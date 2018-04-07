import logging
import time

import cord

logging.basicConfig(level=logging.DEBUG)

with open('token.txt', 'r') as file:
    token = file.read().strip()

PREFIX = 'nya '
EVAL_WHITELIST = (162819866682851329, 69198249432449024)

client = cord.Client(token=token,)
                     #api_root='http://0.0.0.0:8000/api')
log = logging.getLogger(__name__)


@client.on('PROPER_READY')
async def on_ready(payload):
    print(f'Ready! {client.user!r}')


@client.on('TYPING_START')
async def on_typing(payload):
    data = payload['d']
    chan = client.state.get_channel(int(data['channel_id']))
    user = client.state.get_user(int(data['user_id']))
    print('typing', chan, user)


@client.on('MESSAGE_CREATE')
async def on_message(message):
    if message.author.id == client.user.id:
        return

    cnt = message.content
    if not cnt.startswith(PREFIX):
        return

    cnt = cnt[len(PREFIX):]
    args = cnt.split()

    if args[0] == 'ping':
        t1 = time.monotonic()
        msg = await message.reply('.')
        t2 = time.monotonic()

        delta = round((t2 - t1) * 1000, 2)

        await msg.edit(f'took {delta}ms')
    elif args[0] == 'h':
        await message.reply('hewwo')
    elif args[0] == 'off':
        await message.reply('baaai')
        client.disconnect()
    elif args[0] == 'reconn':
        await message.reply('disconnecting ws, wait reconn at any moment')
        await client.ws.close()
    elif args[0] == 'eval':
        if message.author.id not in EVAL_WHITELIST:
            return await message.reply('no \N{ANGER SYMBOL}')
        inputstr = ' '.join(args[1:])
        try:
            res = eval(inputstr)
            await message.reply(f':ok_hand: `{res!r}`')
        except Exception as err:
            await message.reply(f':x: {err!r}')

# @client.on('PRESENCE_UPDATE')
# async def on_presence_update(payload):
#     data = payload['d']
#     guild_id = data.get('guild_id')
#     print(f'Received guild ID {guild_id!r}')
#     if guild_id is None:
#         return

#     if guild_id == '295341979800436736':
#         user = client.state.get_user(data['user'])
#         print(f'Presence for user {user!r}')
#         fmt = f'**{user}** -> {data["status"]}, game object: {data["game"]}'
#         await client.http.post('/channels/324416852744994818/messages',
#                                {'content': fmt})

client.run()


