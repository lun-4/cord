
class Identifiable:
    __slots__ = ('id',)
    def __init__(self, payload):
        self.id = int(payload['id'])

    def __eq__(self, other):
        return self.id == other.id

    def fill(self, raw_object):
        """Fill an object with data.
        
        The object needs to have a _fields attribute, it is a list of strings ot tuples.
        """
        for field in self._fields:
            val = raw_object[field]
            if isinstance(field, tuple):
                setattr(self, field[1], field[0](val))
            else:
                setattr(self, field, val)
            
    def update(self, raw_object):
        """Update an object with new data."""
        try:
            self.fill(raw_object):
        except KeyError:
            pass

class Guild(Identifiable):
    __slots__ = ('name', '')
    def __init__(self, raw_guild):
        super().__init__(raw_guild)
        
        self._fields = ['name', 'region', (int, 'owner_id'), 'verification_level', 
                'features', 'large', 'unavailable', 'members']

        self.fill(raw_guild)
