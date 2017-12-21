import asyncio
import json
import logging
import os
from random import randint

import aiohttp
import websockets

from .http import HTTP
from .op import OP, Disconnect
from .state import State
from .objects import UnavailableGuild, Guild, TextChannel,\
        VoiceChannel, ClientUser, User

log = logging.getLogger('cord.client')
logging.getLogger('websockets').setLevel(logging.INFO)


class Client:
    """Client object for cord.

    Attributes
    ----------
    http: :class:`HTTP`
        HTTP client.
    loop: `event loop`
        asyncio event loop.
    ws: `websocket client`
        websocket connection.
    state: :class:`State`
        Client state
    seq: int
        Sequence number, changed when Discord says it.
    events: dict
        Custom events to event handlers.
    _events: dict
        Gateway events to ``asyncio.Event`` objects.
    heartbeat_task: ``asyncio.Task``
        Heartbeat task.
    """
    def __init__(self, **kwargs):
        self.http = HTTP(**kwargs)
        self.loop = kwargs.get('loop') or asyncio.get_event_loop()
        self.ws = None
        self.seq = None

        self.state = State(self)
        self.user = None
        self.session_id = None

        # actual events
        self.events = {
            'WS_RECEIVE': [],
            'READY': [self.process_ready],
            'RESUMED': [self.process_resumed],

            'GUILD_CREATE': [self.guild_create],
            'GUILD_UPDATE': [self.guild_update],
            'GUILD_DELETE': [self.guild_delete],
        }

        # websocket event objects, asyncio.Event
        self._events = {}

        self.heartbeat_task = None
        self._ack = False

        self.ready = False
        self._ready_task = None

    def on(self, event):
        """Register a event handler.

        Parameters
        ----------
        event: str
            Event name.
        """
        def inner(func):
            if not asyncio.iscoroutinefunction(func):
                raise RuntimeError(
                    'Event callback %s (waits for %s) is not a coroutine' % (func.__qualname__,
                                                                             event))

            log.debug(f'Add event handler for {event.upper()}')
            self.events[event.upper()] = self.events.get(event.upper(), []) + [func]
            return None
        return inner

    async def _send_raw(self, d):
        """Sends encoded JSON data over the websocket.

        Parameters
        ----------
        d: any
            Any object.
        """
        await self.ws.send(json.dumps(d))

    async def heartbeat(self, interval):
        """Heartbeat with Discord.

        Parameters
        ----------
        interval: int
            Heartbeat interval in miliseconds.
        """
        log.debug('Starting to heartbeat at an interval of %d ms.', interval)
        try:
            while True:
                log.debug('Heartbeat! seq = %s', self.seq or '<none>')
                await self._send_raw({'op': OP.HEARTBEAT, 'd': self.seq})

                # Intentional 300ms, gives us time to wait for an ACK.
                await asyncio.sleep(0.3)

                if not self._ack:
                    log.warning('We didn\'t get a response from the gateway.')
                    # should we resume

                self._ack = False
                await asyncio.sleep(interval / 1000)
        except asyncio.CancelledError:
            log.info('Heartbeat cancelled')

    async def heartbeat_ack(self):
        """Acknowledges a heartbeat."""
        log.debug("Acknowledged heartbeat!")
        self._ack = True

    async def recv(self):
        """Receive a payload from the gateway.

        Dispatches ``WS_RECEIVE`` to respective handlers.
        """
        cnt = await self.ws.recv()

        j = json.loads(cnt)

        handlers = self.events.get('WS_RECEIVE', [])
        for func in handlers:
            await func(j)

        return j

    async def process_events(self):
        """Handles payloads from the gateway. """
        try:
            while True:
                j = await self.recv()
                await self.process_packet(j)
        except websockets.ConnectionClosed as err:
            log.exception('Connection failed')
            await self.reconnect(err)

    async def connect(self, gw_version=7):
        """Start a connection to the gateway."""
        gw = await self.http.gateway_url(version=gw_version)
        if not gw:
            log.error('No gateway URL received')
            return

        log.info(f'Connecting to {gw!r}')
        self.ws = await websockets.connect(gw)

    async def identify(self):
        """Send an ``IDENTIFY`` packet."""
        log.info('Identifying with the gateway...')

        await self._send_raw({
            'op': OP.IDENTIFY,
            'd': {
                'token': self.http.token,
                'properties': {
                    '$os': os.name,
                    '$browser': 'cord',
                    '$device': 'cord',
                },
                'compress': False,
                'large_threshold': 250,
                'shard': [0, 1]
            }
        })

        log.info('IDENTIFY Sent')

    async def resume(self):
        """Send a RESUME packet."""
        log.info('Resuming with the gateway')
        log.debug(f'{self.seq}')

        await self._send_raw({
            'op': OP.RESUME,
            'd': {
                'token': self.http.token,
                'session_id': self.session_id,
                'seq': self.seq
            }
        })

        log.info('RESUME sent')

    async def reconnect(self, err: websockets.ConnectionClosed):
        """Start a reconnection."""

        log.info(f'Currently trying to reconnect from {err!r}')

        if err.code in (Disconnect.INVALID_SHARD,
                        Disconnect.SHARDING_REQUIRED):
            log.error('Unrecoverable state (sharding).')
            return

        if err.code in (Disconnect.AUTH_FAIL,):
            log.error('Invalid token')
            return

        if err.code in (Disconnect.AUTH_DUPE,):
            log.error('Duped authentication')

        await self.connect()

        # Depending on the error, we resume or not
        if err.code in (Disconnect.INVALID_SEQ,
                        Disconnect.SESSION_TIMEOUT,
                        Disconnect.RATE_LIMITED):
            log.info('Re-identifying...')
            await self.identify()
        else:
            log.info('Resuming...')
            await self.resume()

        await self.process_events()

    async def process_packet(self, j: dict):
        op = j['op']
        data = j.get('d')
        if op == OP.HELLO:
            await self.process_hello(j)
        elif op == OP.HEARTBEAT_ACK:
            await self.heartbeat_ack()
        elif op == OP.INVALID_SESSION:
            if not data:
                await asyncio.sleep(randint(1, 5))
                await self.identify()
            else:
                await self.resume()
        elif op == OP.RECONNECT:
            await self.ws.close()
            await self.reconnect(websockets.ConnectionClosed(
                code=Disconnect.UNKNOWN, reason='forced reconnect'))
        elif op == OP.DISPATCH:
            # update seq (only update on dispatch)
            if 's' in j:
                log.debug(f'seq: {self.seq} -> {j["s"]}')
                self.seq = j['s']

            try:
                await self.event_dispatcher(j)
            except Exception:
                log.exception('Error dispatching event')

    async def process_hello(self, j):
        """Process an `OP 10 Hello` packet and start a heartbeat task.

        Parameters
        ----------
        j: dict
            The `OP 10 Hello` packet.
        """
        data = j['d']
        hb_interval = data['heartbeat_interval']
        log.debug(f'Got OP hello. Heartbeat interval = {hb_interval} ms.')
        if self.heartbeat_task:
            self.heartbeat_task.cancel()

        self.heartbeat_task = self.loop.create_task(
                self.heartbeat(hb_interval))
        self._ack = True

        if not self.ready:
            await self.identify()

    async def proper_ready_wait(self):
        """Waits for 100ms without any
        GUILD_CREATE events to dispatch
        the `proper_ready` event."""
        if self.ready:
            log.debug('Already PROPER_READY')
            return

        log.info('waiting')
        await asyncio.sleep(1)
        log.info('waited, dispatching')

        await self.event_dispatcher({
            'op': OP.DISPATCH,
            't': 'PROPER_READY',
        })
        self.ready = True

    async def process_ready(self, payload):
        """Process a `READY` event from the gateway.

        Fills in internal cache.
        """

        if not self._ready_task:
            self._ready_task = self.loop.create_task(
                self.proper_ready_wait())

        data = payload['d']

        self.session_id = data['session_id']
        self.user = ClientUser(self, data['user'])

        for raw_guild in data['guilds']:
            if raw_guild['unavailable']:
                unavailable_guild = UnavailableGuild(self, raw_guild)
                self.state.add_guild(unavailable_guild)
                continue

            for raw_channel in raw_guild['channels']:
                raw_channel['guild_id'] = raw_guild['id']
                if raw_channel['type'] == 0:
                    self.state.add_channel(TextChannel(self, raw_channel))
                else:
                    self.state.add_channel(VoiceChannel(self, raw_channel))

            for raw_member in raw_guild['members']:
                self.state.add_user(User(self, raw_member['user']))

            guild = Guild(self, raw_guild)
            self.state.add_guild(guild)

        log.debug(f'Connected to {data["_trace"]}')
        log.info(f'Logged in! {self.user!r}')

        # log.debug(self.channels)
        # log.debug(self.guilds)

    async def process_resumed(self, payload):
        """Process RESUMED event."""
        log.info(f'Resumed with {payload["d"]["_trace"]!r}')

    async def guild_create(self, payload):
        """GUILD_CREATE event handler.

        Fills in the internal guild cache, overwrites
        existing guilds in cache if needed.
        """

        if self._ready_task:
            self._ready_task.cancel()

        raw_guild = payload['d']

        for raw_channel in raw_guild['channels']:
            raw_channel['guild_id'] = raw_guild['id']
            if raw_channel['type'] == 0:
                self.state.add_channel(TextChannel(self, raw_channel))
            else:
                self.state.add_channel(VoiceChannel(self, raw_channel))

        for raw_member in raw_guild['members']:
            self.state.add_user(User(self, raw_member['user']))

        guild = Guild(self, raw_guild)
        self.state.add_guild(guild)

        self._ready_task = self.loop.create_task(
            self.proper_ready_wait())

    async def guild_update(self, payload):
        """GUILD_UPDATE event handler.

        Updates a guild.
        """
        self.state.update_guild(payload['d'])

    async def guild_delete(self, payload):
        """GUILD_DELETE event handler.

        Deletes a guild from cache.
        """
        self.state.delete_guild(int(payload['d']['id']))

    async def wait_event(self, evt_name):
        """Wait for a dispatched event from the gateway.

        Parameters
        ----------
        evt_name: str
            Event to wait.
        """
        evt_name = evt_name.upper()

        if evt_name not in self._events:
            self._events[evt_name] = asyncio.Event(loop=self.loop)

        await self._events[evt_name].wait()

    async def event_dispatcher(self, payload):
        """Dispatch an event.

        Parameters
        ----------
        payload: dict
            Payload.
        """

        if payload['op'] != OP.DISPATCH:
            return

        evt_name = payload['t']

        try:
            self._events[evt_name].set()
        except KeyError:
            pass

        # log.debug(f'Event Dispatcher: {evt_name}')
        callbacks = self.events.get(evt_name, [])
        args = [payload]

        if evt_name == 'MESSAGE_CREATE':
            args = [self.state.get_message(payload['d'])]

        for callback in callbacks:
            await callback(*args)

    async def _run(self, gw_version=7):
        # create http clientsession
        self.http.session = aiohttp.ClientSession()
        await self.connect()
        await self.process_events()

    async def close(self):
        """Closes the client."""
        log.info('Closing the client...')

        # cancel heartbeater
        if self.heartbeat_task:
            self.heartbeat_task.cancel()

        # close ws
        if self.ws is not None:
            await self.ws.close()

        # close aiohttp clientsession
        self.http.session.close()

    async def disconnect(self):
        """Closes the connection to Discord."""
        await self.close()

    def run(self, gw_version=7):
        """Runs the client."""
        try:
            self.loop.run_until_complete(self._run(gw_version))
        finally:
            log.info('Closing.')

            log.info('Closing loop...')
            self.loop.close()
