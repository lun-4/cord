import logging

log = logging.getLogger('cord.objects')

class Identifiable:
    def __init__(self, payload):
        self.id = int(payload['id'])

    def __eq__(self, other):
        return self.id == other.id

    def __repr__(self):
        return f'Identifiable({self.id})'

    def fill(self, raw_object):
        """Fill an object with data.
        
        The object needs to have a _fields attribute, it is a list of strings ot tuples.
        """
        for field in self._fields:
            if isinstance(field, tuple):
                val = raw_object[field[1]]
                setattr(self, field[1], field[0](val))
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
    def __init__(self, raw_guild):
        super().__init__(raw_guild)
        
        self._fields = ['name', 'region', (int, 'owner_id'), 'verification_level', 
                'features', 'large', 'unavailable', 'members']

        self.fill(raw_guild)

class ClientUser(Identifiable):
    def __init__(self, raw_user):
        super().__init__(raw_user)

        self._fields = ['username', 'discriminator', 'avatar', 'bot', 'verified', 'email']

        self.fill(raw_user)

    def __repr__(self):
        return f'ClientUser({self.username!r}#{self.discriminator!r})'
