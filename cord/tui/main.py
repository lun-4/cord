import asyncio
import logging

import urwid

from ..client import Client

logging.basicConfig(level=logging.DEBUG)

log = logging.getLogger('cord.tui')

def unhandled(key):
    if key == 'ctrl c':
        raise urwid.ExitMainLoop

class TUIClient:
    def __init__(self, **kwargs):
        self.client = Client(**kwargs)
        self.loop = self.client.loop

    async def close(self):
        """Closes"""
        log.info('Calling a client close')
        await self.client.close()

    def main_screen(self):
        txt = urwid.Text(u"Hello World")
        fill = urwid.Filler(txt, 'top')
        return fill

    def start(self, gw_version=6):
        """Starts the event loop"""
        log.info('Starting loop')
        self.loop.create_task(self.client._run(gw_version=gw_version))

        masked_loop = urwid.AsyncioEventLoop(loop=self.loop)

        urwid_loop = urwid.MainLoop(
            self.main_screen(),
            event_loop=masked_loop,
            unhandled_input=unhandled,
        )

        try:
            log.info('Running loop.')
            with urwid_loop.start():
                self.loop.run_forever()
        except:
            log.info('Exiting')
            self.loop.run_until_complete(self.loop.create_task(self.close()))
            self.loop.close()
            log.info('Closed!')
            return
