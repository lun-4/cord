class HTTP:
    def __init__(self, *, token):
        self.token = token
        self.endpoint_root = 'https://discordapp.com/api'
        self.session = None

    def route(self, path: str = '') -> str:
        """Returns an API endpoint."""
        return self.endpoint_root + path

    async def gateway_url(self, *, version=7, encoding='json') -> str:
        """Returns the gateway URL used for connecting to the gateway."""
        async with self.session.get(self.route('/gateway')) as resp:
            return (await resp.json())['url'] + '?v=%d&encoding=%s' % (version, encoding)

