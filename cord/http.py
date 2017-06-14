import logging
import json

log = logging.getLogger(__name__)

VERSION = '0.0.1'


class HTTP:
    def __init__(self, **kwargs):
        self.api_root = kwargs.get('api_root') or 'https://discordapp.com/api'
        self.token = kwargs.get('token')
        self.email = kwargs.get('email')
        self.password = kwargs.get('password')
        self.session = None

        self.user_agent = f'DiscordBot (cord, {VERSION})'


    def get_headers(self):
        return {
            'User-Agent': self.user_agent,
            'Authorization': f'Bot {self.token}'
        }

    def route(self, path: str = '') -> str:
        """Returns an API endpoint."""
        return self.api_root + path

    async def gateway_url(self, *, version=7, encoding='json') -> str:
        """Returns the gateway URL used for connecting to the gateway."""

        # automatic login if needed.
        if self.token is None:
            await self.login()

        if self.token is None:
            log.error('No token specified.')
            return

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

    async def request(self, method, path, data=None):
        """Make a request to the API.

        Parameters
        ----------
        method: str
            Method to be used in the request.
        path: str
            Path of the route to be called.
        """

        headers = self.get_headers()
        if data is not None:
            headers['Content-Type'] = 'application/json'
            data = json.dumps(data, separators=(',', ':'))

        async with self.session.request(method, self.route(path), headers=headers, data=data) as resp:
            log.debug(f'Requested {method}:{path}, {resp!r}')
            try:
                output_data = await resp.json()
            except:
                pass

            if resp.status == 200:
                log.debug(f'{method}:{path} with {data} returned {output_data}')
                return output_data

    async def get(self, path, data=None):
        return await self.request('GET', path, data)

    async def post(self, path, data=None):
        return await self.request('POST', path, data)

    async def put(self, path, data=None):
        return await self.request('PUT', path, data)

    async def delete(self, path, data=None):
        return await self.request('DELETE', path, data)
