class OP:
    """OP code reference."""
    DISPATCH = 0
    HEARTBEAT = 1
    IDENTIFY = 2
    STATUS_UPDATE = 3
    RESUME = 6
    RECONNECT = 7
    REQUEST_GUILD_MEMBERS = 8
    INVALID_SESSION = 9
    HELLO = 10
    HEARTBEAT_ACK = 11


class Disconnect:
    UNKNOWN = 4000

    # Authentication failed
    # We should NOT reconnect.
    AUTH_FAIL = 4004

    # We SHOULD reconnect in this, though
    AUTH_DUPE = 4005

    # We sent an invalid OP code
    # OR json decoding fucked up.
    #  Should we reconnect?
    OPCODE_ERROR = 4001
    DECODE_ERROR = 4002

    # Reconnect.
    INVALID_SEQ = 4007
    RATE_LIMITED = 4008
    SESSION_TIMEOUT = 4009

    # Do not reconnect.
    INVALID_SHARD = 4010
    SHARDING_REQUIRED = 4011
