class HTTP:
    def __init__(self, *, token, api_root = 'https://discordapp.com/api'):
        self.token = token
        self.api_root = api_root
        self.session = None

    def route(self, path: str = '') -> str:
        """Returns an API endpoint."""
        return self.api_root + path

    async def gateway_url(self, *, version=7, encoding='json') -> str:
        """Returns the gateway URL used for connecting to the gateway."""
        async with self.session.get(self.route('/gateway')) as resp:
            return (await resp.json())['url'] + '?v=%d&encoding=%s' % (version, encoding)
