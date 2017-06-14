from .utils import delete, get
from .objects import UnavailableGuild, Guild, User, Message

class State:
    def __init__(self, client):
        self.client = client

        # Client's internal cache, Client.process_ready fills them
        self.guilds = []
        self.channels = []
        self.user = None
        
        # Those caches are filled on-the-fly through message events and user objects
        self.messages = []
        self.users = []

    def add_guild(self, guild):
        """Adds a guild to the internal cache, if it already exists, it gets updated.

        Parameters
        ----------
        guild: :class:`Guild`
            Guild object to be added
        """
        old_guild = get(self.guilds, id=guild.id)

        # Check to overwrite unavailable guilds with new shiny guild objects
        if isinstance(old_guild, UnavailableGuild) and isinstance(guild, Guild):
            delete(self.guilds, id=guild.id)
            self.guilds.append(guild)
            return

        if old_guild is not None:
            old_guild.update(guild._raw)
            return

        self.guilds.append(guild)

    def update_guild(self, raw_guild):
        """Updates a guild in internal cache, if it doesn't exist, doesn't do anything.

        Parameters
        ----------
        raw_gulid: dict
            Raw guild object.
        """

        guild = get(self.guilds, id=int(raw_guild['id']))
        if guild is None:
            return

        guild.update(raw_guild)

    def get_guild(self, guild_id: int):
        """Get a Guild from its ID."""
        return delete(self.guilds, id=guild_id)

    def delete_guild(self, guild_id: int):
        """Delete a guild from internal cache from its ID."""
        delete(self.guilds, id=guild_id)

    def add_channel(self, channel):
        """Adds a channel to the internal cache, if it already exists, it gets updated.

        Parameters
        ----------
        channel: :class:`Channel`
            Channel object to be added.
        """
        old_channel = get(self.channels, id=channel.id)

        if old_channel is not None:
            old_channel.update(channel._raw)
            return

        self.channels.append(channel)

    def update_channel(self, raw_channel):
        """Updates a channel in internal cache, if it doesn't exist, doesn't do anything.

        Parameters
        ----------
        raw_channel: dict
            Raw guild object.
        """

        channel = get(self.channels, id=int(raw_channel['id']))
        if channel is None:
            return

        channel.update(raw_channel)

    def get_channel(self, channel_id: int):
        """Get a channel by its ID."""
        return get(self.channels, id=channel_id)

    def delete_channel(self, channel_id: int):
        """Delete a channel from internal cache from its ID."""
        delete(self.channels, id=channel_id)

    def add_user(self, user: User):
        """Add a user to the cache, updates if needed."""
        old_user = get(self.users, id=user.id)
        if old_user is not None:
            old_user.update(user._raw)

        self.users.append(user)

    def update_user(self, raw_user: dict):
        """Update a user in the cache,"""

        user = get(self.users, id=int(raw_user['id']))
        if user is None:
            return
        
        user.update(raw_user)
    
    def get_user(self, user):
        """Get a user object from the cache.
        
        If the user is a dict, this calls :meth:`Client.add_user` and returns it.

        Returns
        -------
        :class:`User`
        """
        if isinstance(user, dict):
            self.add_user(User(self.client, user))
            return get(self.users, id=int(user['id']))

        return get(self.users, id=int(user))

    def delete_user(self, user_id: int):
        """Delete a user from the cache."""
        delete(self.users, id=user_id)

    def add_message(self, message: Message):
        """Add a message to the message cache, updates if needed."""
        old_message = get(self.messages, id=message.id)
        if old_message is not None:
            old_message.update(message._raw)
            return

        self.messages.append(message)

    def update_message(self, raw_message: dict):
        """Update a message in the internal cache."""
        message = get(self.messages, id=int(raw_message['id']))
        if message is None:
            return

        message.update(raw_message)

    def get_message(self, message):
        """Get a message from the cache.
        
        If message is a dict, this calls :meth:`Client.adD_message` first.

        Parameters
        ----------
        message: dict, int or str
            Message ID to be searched.

        Returns
        -------
        :class:`Message`
        """
        if isinstance(message, dict):
            self.add_message(Message(self.client, message))
            return self.get_message(message['id'])

        return get(self.messages, id=int(message))

    def delete_message(self, message_id: int):
        """Delete a message from message cache."""
        delete(self.messages, id=message_id)
