import aiohttp
import asyncio
import websockets

import json
import logging
import os

from .http import HTTP
from .op import OP

log = logging.getLogger('cord.client')


class Client:
    def __init__(self, *, token, **kwargs):
        self.http = HTTP(token=token, **kwargs)
        self.loop = asyncio.get_event_loop()
        self.ws = None
        self.seq = None

        # actual events
        self.events = {
            'WS_RECEIVE': [self.event_dispatcher],
        }

        # websocket event objects, asyncio.Event
        self._events = {}

        self._heartbeat_task = None

        # if this client is running under custom WS logic
        self.custom_ws_logic = False

    def on(self, event):
        def inner(func):
            if not asyncio.iscoroutinefunction(func):
                raise RuntimeError(
                    'Event callback %s (waits for %s) is not a coroutine' % (func.__qualname__,
                                                                             event))
            self.events[event.upper()] = self.events.get(event.upper(), []) + [func]
            return None
        return inner

    async def _send_raw(self, d):
        """Sends encoded JSON data over the websocket."""
        await self.ws.send(json.dumps(d))

    async def _heartbeat(self, interval):
        log.debug('Starting to heartbeat at an interval of %d ms.', interval)
        while True:
            log.debug('Heartbeat! seq = %s', self.seq or '<none>')
            await self._send_raw({'op': OP.HEARTBEAT, 'd': self.seq})
            await asyncio.sleep(interval / 1000)

    async def identify(self):
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
        try:
            cnt = await self.ws.recv()
        except websockets.exceptions.ConnectionClosed:
            return

        j = json.loads(cnt)
        log.debug('Websocket receive: %s', j)

        handlers = self.events.get('WS_RECEIVE', [])
        for func in handlers:
            await func(j)

        return j

    async def default_receiver(self):
        # default websocket logic
        while True:
            j = await self.recv_payload()

            # update seq
            if 's' in j:
                log.debug('Seq: %s -> %s', self.seq or '<none>', j['s'] or '<none>')
                self.seq = j['s']

            if not self.custom_ws_logic:
                if j['op'] == OP.HELLO:
                    await self.process_hello(j)
                elif j['op'] == OP.DISPATCH:
                    await self.event_dispatcher(j)

    async def process_hello(self, j):
        hb_interval = j['d']['heartbeat_interval']
        log.debug('Got OP hello. Heartbeat interval = %d ms.', hb_interval)
        log.debug('Creating heartbeat task.')
        self._heartbeat_task = self.loop.create_task(self._heartbeat(hb_interval))

        if not self.custom_ws_logic:
            await self.identify()

    async def wait_event(self, evt_name):
        evt_name = evt_name.upper()

        if evt_name not in self._events:
            self._events[evt_name] = asyncio.Event(loop=self.loop)

        await self._events[evt_name].wait()

    async def event_dispatcher(self, payload):
        log.debug('[e_dispatcher] RECV PAYLOAD')
        if payload['op'] != OP.DISPATCH:
            log.debug("[e_dispatcher] Not DISPATCH, ignoring")
            return

        try:
            self._events[payload['t']].set()
        except KeyError:
            pass

        callbacks = self.events.get(payload['t'], [])
        for callback in callbacks:
            await callback()

    async def _run(self, gw_version=7):
        # create http clientsession
        self.http.session = aiohttp.ClientSession()

        # grab the gateway url, then connect
        gw = await self.http.gateway_url(version=gw_version)
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
        await self.ws.close()

        # close aiohttp clientsession
        log.debug('Closing procedure: Closing ClientSession...')
        self.http.session.close()

        log.debug('Closing procedure: Complete!')

    def run(self, gw_version=7):
        """Runs the client."""
        self.loop.create_task(self._run(gw_version))
        try:
            self.loop.run_forever()
        finally:
            log.info('Closing.')

            # close everything
            self.loop.run_until_complete(self.loop.create_task(self.close()))

            log.info('Closing loop...')
            self.loop.close()
