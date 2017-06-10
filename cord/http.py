import json

class HTTP:
    def __init__(self, **kwargs):
        self.api_root = kwargs.get('api_root') or 'https://discordapp.com/api'
        self.token = kwargs.get('token')
        self.email = kwargs.get('email')
        self.password = kwargs.get('password')
        self.session = None

    def route(self, path: str = '') -> str:
        """Returns an API endpoint."""
        return self.api_root + path

    async def gateway_url(self, *, version=7, encoding='json') -> str:
        """Returns the gateway URL used for connecting to the gateway."""

        # automatic login if needed.
        if self.token is None:
            await self.login()

        async with self.session.get(self.route('/gateway')) as resp:
            return (await resp.json())['url'] + f'?v={version}&encoding={encoding}'

    async def login(self):
        """Gets a token using the auth endpoint."""

        if 'discordapp' in self.api_root:
            log.warning('Won\'t use user/pass login on discord.')
            return

        _payload = {
            'email': self.email,
            'password': self.password,
        }

        async with self.session.post(self.route('/auth/login'), data=json.dumps(_payload)) as resp:
            j = await resp.json()
            self.token = j['token']

    async def get(self, path):
        """Makes a GET request.

        Returns
        -------
        dict:
            JSON data returned from the request.
        """
        async with self.session.get(self.route(path)) as resp:
            return await resp.json()
