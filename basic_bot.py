import logging

import cord

logging.basicConfig(level=logging.DEBUG)

client = cord.Client(token='MzE2NjAyOTAxMjY5MzE1NTk1.DCIHJg.rESj3cnQKSwfxGZn9Bdtp2JeuzY')

@client.on('READY')
async def on_ready(payload):
    print(f'Ready! {client.user!r}')

@client.on('MESSAGE_CREATE')
async def on_message(message):
    print(f'{message!r}')

client.run()


