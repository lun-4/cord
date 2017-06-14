import aiohttp
import asyncio
import websockets

import json
import logging
import os

from .http import HTTP
from .op import OP
from .state import State
from .objects import UnavailableGuild, Guild, TextChannel, VoiceChannel, ClientUser, User

log = logging.getLogger('cord.client')


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

            'GUILD_CREATE': [self.guild_create],
            'GUILD_UPDATE': [self.guild_update],
            'GUILD_DELETE': [self.guild_delete],
        }

        # websocket event objects, asyncio.Event
        self._events = {}

        self.heartbeat_task = None
        self._ack = False

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
        while True:
            log.debug('Heartbeat! seq = %s', self.seq or '<none>')
            await self._send_raw({'op': OP.HEARTBEAT, 'd': self.seq})

            # Intentional 300ms, gives us time to wait for an ACK.
            await asyncio.sleep(0.3)

            if not self._ack:
                log.warning('We didn\'t get a response from the gateway.')

            self._ack = False
            await asyncio.sleep(interval / 1000)

    async def heartbeat_ack(self):
        """Acknowledges a heartbeat."""
        log.debug("Acknowledged heartbeat!")
        self._ack = True

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
                    '$referrer': '',
                    '$referring_domain': ''
                },
                'compress': False,
                'large_threshold': 250,
                'shard': [0, 1]
            }
        })

    async def recv_payload(self):
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
                j = await self.recv_payload()

                # update seq
                if 's' in j:
                    log.debug(f'seq: {self.seq} -> {j["s"]}')
                    self.seq = j['s']

                op = j['op']
                if op == OP.HELLO:
                    await self.process_hello(j)
                elif op == OP.HEARTBEAT_ACK:
                    await self.heartbeat_ack()
                elif op == OP.DISPATCH:
                    try:
                        await self.event_dispatcher(j)
                    except:
                        log.exception('Error dispatching event')
        except websockets.ConnectionClosed as err:
            return

    async def process_hello(self, j):
        """Process an `OP 10 Hello` packet and start a heartbeat task.

        Parameters
        ----------
        j: dict
            The `OP 10 Hello` packet.
        """
        hb_interval = j['d']['heartbeat_interval']
        log.debug('Got OP hello. Heartbeat interval = %d ms.', hb_interval)
        log.debug('Creating heartbeat task.')
        self.heartbeat_task = self.loop.create_task(self.heartbeat(hb_interval))
        self._ack = True

        await self.identify()

    async def process_ready(self, payload):
        """Process a `READY` event from the gateway.

        Fills in internal cache.
        """

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

        log.debug(f'Connected to {",".join(data["_trace"])}')
        log.info(f'Logged in! {self.user!r}')

        #log.debug(self.channels)
        #log.debug(self.guilds)

    async def guild_create(self, payload):
        """GUILD_CREATE event handler.

        Fills in the internal guild cache, overwrites
        existing guilds in cache if needed.
        """

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

        log.debug(f'Event Dispatcher: {evt_name}')
        callbacks = self.events.get(evt_name, [])
        args = [payload]

        if evt_name == 'MESSAGE_CREATE':
            args = [self.state.get_message(payload['d'])]

        for callback in callbacks:
            await callback(*args)

    async def _run(self, gw_version=7):
        # create http clientsession
        self.http.session = aiohttp.ClientSession()

        # grab the gateway url, then connect
        gw = await self.http.gateway_url(version=gw_version)
        if gw is None:
            log.error('No gateway URL received.')
            return

        log.info('Connecting to gateway: %s', gw)
        self.ws = await websockets.connect(gw)

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
