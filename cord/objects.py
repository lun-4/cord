import logging

log = logging.getLogger('cord.objects')

def make_channels(raw_channels, client):
    return [client.get_channel(int(chan['id'])) for chan in raw_channels]

class Identifiable:
    def __init__(self, client, payload):
        self.id = int(payload['id'])
        self._raw = payload
        self.client = client

    def __eq__(self, other):
        return self.id == other.id

    def __repr__(self):
        return f'Identifiable({self.id})'

    def fill(self, raw_object):
        """Fill an object with data.

        The object needs to have a _fields attribute, it is a list of strings or tuples.
        """
        for field in self._fields:
            if isinstance(field, tuple):
                val = raw_object[field[1]]
                setattr(self, field[1], field[0](val, *field[2:]))
            else:
                val = raw_object[field]
                setattr(self, field, val)

    def update(self, raw_object):
        """Update an object with new data."""
        try:
            self.fill(raw_object)
        except KeyError:
            pass

class Guild(Identifiable):
    """Guild object.

    Attributes
    ----------
    name: str
        Guild name.
    region: str
        Guild's voice region.
    owner_id: int
        Guild's owner, as a snowflake ID.
    verification_level: int
        Guild's verification level.
    features: List[str]
        Guild features.
    large: bool
        True if the guild is large.
    unavailable: bool
        If the guils is unavailable to the client.
    members: List[Member]
        Guild members.
    channels: List[Channel]
        Guild channels.
    """
    def __init__(self, client, raw_guild):
        super().__init__(client, raw_guild)

        self._fields = ['name', 'region', (int, 'owner_id'), 'verification_level',
                'features', 'large', 'unavailable', 'members', (make_channels, 'channels', client)]

        self.fill(raw_guild)

    def __repr__(self):
        return f'Guild({self.id}, {self.name})'

class Channel(Identifiable):
    """A text channel."""
    def __init__(self, client, raw_channel):
        super().__init__(client, raw_channel)

        self._fields = [(int, 'guild_id'), 'name', 'type', 'position', 'is_private', 'topic', (int, 'last_message_id')]

        # We update instad of filling initially becaue of voice channels
        # that don't have topic or last_message_id
        self.update(raw_channel)

        self.guild = client.get(client.guilds, id=self.guild_id)

    def __repr__(self):
        return f'Channel({self.id}, {self.name})'

class User(Identifiable):
    def __init__(self, client, raw_user):
        super().__init__(client, raw_user)

        self._fields = ['username', 'discriminator', 'avatar', 'bot', 'verified', 'email']

        self.update(raw_user)

    def __repr__(self):
        return f'ClientUser({self.username}#{self.discriminator})'

class Member(Identifiable):
    """General member object."""
    def __init__(self, client, raw_member):
        super().__init__(client, raw_member)

        self._fields = ['nick', 'joined_at']

        self.fill(raw_member)
