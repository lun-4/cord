import logging

import cord.client
from cord.op import OP

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

client = cord.client.Client(token='litecord_RLoWjnc45pDX2shufGjijfyPbh2kV0sYGz2EwARhIAs=',
                            api_root='http://0.0.0.0:8000/api')

@client.on('READY')
async def on_ready():
    print("Received READY event")

@client.on('websocket_connect')
async def on_ws_connect():
    """Control how the websocket works.

    This event is fired when the websocket connects with a Discord-compatible gateway server.
    If there isn't any handler for this event, ``goodshit`` will do its default.

    With this event you can customize how the websocket actually connects with the gateway.
    """

    hello_packet = await client.recv_payload()

    # this will start heartbeating
    await client.process_hello(hello_packet)

    # this will properly identify with the gateway using the token
    log.info("Identifying")
    await client.identify()

    client.loop.create_task(client.default_receiver())

    # wait this until client receives READY event
    log.info("Waiting for READY")
    await client.wait_event('READY')

    # ratelimit 101
    for i in range(0, 150):
        await client._send_raw({'op': OP.HEARTBEAT, 'd': 'get rekt'})

client.run(gw_version=6)
