import logging

import cord

logging.basicConfig(level=logging.DEBUG)

client = cord.Client(token='MzE2NjAyOTAxMjY5MzE1NTk1.DCIHJg.rESj3cnQKSwfxGZn9Bdtp2JeuzY')

@client.on('READY')
async def on_ready(payload):
    print(f'Ready! {client.user!r}')

@client.on('MESSAGE_CREATE')
async def on_message(message):
    args = message.content.split()
    if message.content.startswith('!wew'):
        await message.reply('u just got meme\'d (from cord)')
    elif args[0] == '!off':
        if message.author.id != 162819866682851329:
            await message.reply('reee')
            return


        client.finish()
        return
    elif args[0] == '!eval':
        if message.author.id != 162819866682851329:
            await message.reply('u suck')
            return

        inputstr = ' '.join(args[1:])
        try:
            res = eval(inputstr)
            await message.reply(f'`{res!r}`')
        except Exception as err:
            await message.reply(f'{err!r}')

@client.on('PRESENCE_UPDATE')
async def on_presence_update(payload):
    data = payload['d']
    guild_id = data.get('guild_id')
    print(f'Received guild ID {guild_id!r}')
    if guild_id is None:
        return

    if guild_id == '295341979800436736':
        user = client.get_user(data['user'])
        print(f'Presence for user {user!r}')
        fmt = f'**{user}** -> {data["status"]}, game object: {data["game"]}'
        await client.http.post('/channels/324416852744994818/messages', {'content': fmt})

client.run()

