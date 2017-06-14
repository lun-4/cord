import aiohttp
import asyncio
import websockets

import json
import logging
import os

from .http import HTTP
from .op import OP
from .objects import UnavailableGuild, Guild, Channel, ClientUser, User, Member, Message


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
    seq: int
        Sequence number, changed when Discord says it.
    events: dict
        Custom events to event handlers.
    _events: dict
        Gateway events to ``asyncio.Event`` objects.
    _heartbeat_task: ``asyncio.Task``
        Heartbeat task.
    custom_ws_logic: bool
        Flag if this client is running custom websocket logic and
        it won't use the deafults provided here.
    """
    def __init__(self, **kwargs):
        self.http = HTTP(**kwargs)
        self.loop = kwargs.get('loop') or asyncio.get_event_loop()
        self.ws = None
        self.seq = None

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

        self._heartbeat_task = None
        self._ack = False

        # if this client is running under custom WS logic
        self.custom_ws_logic = False

        # Client's internal cache, Client.process_ready fills them
        self.guilds = []
        self.channels = []
        self.user = None
        
        # Those caches are filled on-the-fly through message events and user objects
        self.messages = []
        self.users = []

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

    def get(self, lst, **kwargs):
        """Get an object from a list that matches the search criteria in ``**kwargs``.

        Parameters
        ----------
        lst: list
            List to be searched.
        """

        for element in lst:
            for attr, val in kwargs.items():
                res = getattr(element, attr)
                if res == val:
                    return element

        return None

    def delete(self, lst, **kwargs):
        """Delete an element from a list that matches the search criteria in ``**kwargs``

        Parameters
        ----------
        lst: list
            List to be searched.
        """

        for (idx, element) in enumerate(lst):
            for attr, val in kwargs.items():
                res = getattr(element, attr)
                if res == val:
                    del lst[idx]

    async def _send_raw(self, d):
        """Sends encoded JSON data over the websocket.

        Parameters
        ----------
        d: any
            Any object.
        """
        await self.ws.send(json.dumps(d))

    async def _heartbeat(self, interval):
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

    async def _heartbeat_ack(self):
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

    async def default_receiver(self):
        """Default websocket logic.

        If a client has no handlers for ``WEBSOCKET_CONNECT``, this function manages
        `OP 10 Hello` and `OP 0 Dispatch` packets, if not, this is just an infinite loop
        with calls to :py:meth:`Client.recv_payload`.
        """
        log.info(f'Starting default receiver. Custom WS: {self.custom_ws_logic}')
        try:
            while True:
                j = await self.recv_payload()

                # update seq
                if 's' in j:
                    log.debug(f'seq: {self.seq} -> {j["s"]}')
                    self.seq = j['s']

                if not self.custom_ws_logic:
                    op = j['op']
                    if op == OP.HELLO:
                        await self.process_hello(j)
                    elif op == OP.HEARTBEAT_ACK:
                        await self._heartbeat_ack()
                    elif op == OP.DISPATCH:
                        try:
                            await self.event_dispatcher(j)
                        except:
                            log.error('Error dispatching event', exc_info=True)
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
        self._heartbeat_task = self.loop.create_task(self._heartbeat(hb_interval))
        self._ack = True

        if not self.custom_ws_logic:
            await self.identify()

    def add_guild(self, guild):
        """Adds a guild to the internal cache, if it already exists, it gets updated.

        Parameters
        ----------
        guild: :class:`Guild`
            Guild object to be added
        """
        old_guild = self.get(self.guilds, id=guild.id)

        # Check to overwrite unavailable guilds with new shiny guild objects
        if isinstance(old_guild, UnavailableGuild) and isinstance(guild, Guild):
            self.delete(self.guilds, id=guild.id)
            self.guilds.append(guild)
            return

        if old_guild is not None:
            old_guild.update(guild._raw)
            return

        self.guilds.append(guild)

    def update_guild(self, raw_guild):
        """Updates a guild in internal cache, if it doesn't exist, doesn't do anything.

        Parameters
        ----------
        raw_gulid: dict
            Raw guild object.
        """

        guild = self.get(self.guilds, id=int(raw_guild['id']))
        if guild is None:
            return

        guild.update(raw_guild)

    def get_guild(self, guild_id: int):
        """Get a Guild from its ID."""
        return self.get(self.guilds, id=guild_id)

    def delete_guild(self, guild_id: int):
        """Delete a guild from internal cache from its ID."""
        self.delete(self.guilds, id=guild_id)

    def add_channel(self, channel):
        """Adds a channel to the internal cache, if it already exists, it gets updated.

        Parameters
        ----------
        channel: :class:`Channel`
            Channel object to be added.
        """
        old_channel = self.get(self.channels, id=channel.id)

        if old_channel is not None:
            old_channel.update(channel._raw)
            return

        self.channels.append(channel)

    def update_channel(self, raw_channel):
        """Updates a channel in internal cache, if it doesn't exist, doesn't do anything.

        Parameters
        ----------
        raw_channel: dict
            Raw guild object.
        """

        channel = self.get(self.channels, id=int(raw_channel['id']))
        if channel is None:
            return

        channel.update(raw_channel)

    def get_channel(self, channel_id: int):
        """Get a channel by its ID."""
        return self.get(self.channels, id=channel_id)

    def delete_channel(self, channel_id: int):
        """Delete a channel from internal cache from its ID."""
        self.delete(self.channels, id=channel_id)

    def add_user(self, user: User):
        """Add a user to the cache, updates if needed."""
        old_user = self.get(self.users, id=user.id)
        if old_user is not None:
            old_user.update(user._raw)

        self.users.append(user)

    def update_user(self, raw_user: dict):
        """Update a user in the cache,"""

        user = self.get(self.users, id=int(raw_user['id']))
        if user is None:
            return
        
        user.update(raw_user)
    
    def get_user(self, user):
        """Get a user object from the cache.
        
        If the user is a dict, this calls :meth:`Client.add_user` and returns it.

        Returns
        -------
        :class:`User`
        """
        if isinstance(user, dict):
            self.add_user(User(self, user))
            return self.get(self.users, id=int(user['id']))

        return self.get(self.users, id=int(user))

    def delete_user(self, user_id: int):
        """Delete a user from the cache."""
        self.delete(self.users, id=user_id)

    def add_message(self, message: Message):
        """Add a message to the message cache, updates if needed."""
        old_message = self.get(self.messages, id=message.id)
        if old_message is not None:
            old_message.update(message._raw)
            return

        self.messages.append(message)

    def update_message(self, raw_message: dict):
        """Update a message in the internal cache."""
        message - sekf.get(self.messages, id=int(raw_message['id']))
        if message is None:
            return

        message.update(raw_message)

    def get_message(self, message):
        """Get a message from the cache.
        
        If message is a dict, this calls :meth:`Client.adD_message` first.

        Parameters
        ----------
        message: dict, int or str
            Message ID to be searched.

        Returns
        -------
        :class:`Message`
        """
        if isinstance(message, dict):
            self.add_message(Message(self, message))
            return self.get_message(message['id'])

        return self.get(self.messages, id=int(message))

    def delete_message(self, message_id: int):
        """Delete a message from message cache."""
        self.delete(self.messages, id=message_id)

    async def process_ready(self, payload):
        """Process a `READY` event from the gateway.

        Fills in internal cache.
        """

        data = payload['d']

        self.raw_user = data['user']
        self.session_id = data['session_id']

        self.user = ClientUser(self, data['user'])

        for raw_guild in data['guilds']:
            if raw_guild['unavailable']:
                unavailable_guild = UnavailableGuild(self, raw_guild)
                self.add_guild(unavailable_guild)
                continue

            for raw_channel in raw_guild['channels']:
                raw_channel['guild_id'] = raw_guild['id']
                self.add_channel(Channel(self, raw_channel))

            for raw_member in raw_guild['members']:
                self.add_user(User(self, raw_member['user']))

            guild = Guild(self, raw_guild)
            self.add_guild(guild)

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
            self.add_channel(Channel(self, raw_channel))

        for raw_member in raw_guild['members']:
            self.add_user(User(self, raw_member['user']))

        guild = Guild(self, raw_guild)

        self.add_guild(guild)

    async def guild_update(self, payload):
        """GUILD_UPDATE event handler.

        Updates a guild.
        """
        self.update_guild(payload['d'])

    async def guild_delete(self, payload):
        """GUILD_DELETE event handler.

        Deletes a guild from cache.
        """
        self.delete_guild(int(payload['d']['id']))

    async def wait_event(self, evt_name):
        """Wait for a dispatched event from the gateway.

        If using custom WS logic, start :py:meth:`Client.default_receiver`
        so it correctly manages events.

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
            args = [self.get_message(payload['d'])]

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

        callbacks = self.events.get('WEBSOCKET_CONNECT', [])
        for callback in callbacks:
            self.custom_ws_logic = True
            await callback()

        if self.custom_ws_logic:
            return

        await self.default_receiver()

    async def close(self):
        """Closes the client."""
        log.info('Closing the client...')

        log.debug('Closing procedure: Closing heartbeater task...')
        # cancel heartbeater
        if self._heartbeat_task:
            self._heartbeat_task.cancel()

        # close ws
        log.debug('Closing procedure: Closing websocket...')
        if self.ws is not None:
            await self.ws.close()

        # close aiohttp clientsession
        log.debug('Closing procedure: Closing ClientSession...')
        self.http.session.close()

        log.debug('Closing procedure: Complete!')

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
