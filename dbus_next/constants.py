from enum import Enum, IntFlag


class BusType(Enum):
    SESSION = 1
    SYSTEM = 2


class MessageType(Enum):
    METHOD_CALL = 1
    METHOD_RETURN = 2
    ERROR = 3
    SIGNAL = 4


class MessageFlag(IntFlag):
    NONE = 0
    NO_REPLY_EXPECTED = 1
    NO_AUTOSTART = 2
    ALLOW_INTERACTIVE_AUTHORIZATION = 4


class NameFlag(IntFlag):
    NONE = 0
    ALLOW_REPLACEMENT = 1
    REPLACE_EXISTING = 2
    DO_NOT_QUEUE = 4


class RequestNameReply(Enum):
    PRIMARY_OWNER = 1
    IN_QUEUE = 2
    EXISTS = 3
    ALREADY_OWNER = 4


class ReleaseNameReply(Enum):
    RELEASED = 1
    NON_EXISTENT = 2
    NOT_OWNER = 3


class PropertyAccess(Enum):
    READ = 'read'
    WRITE = 'write'
    READWRITE = 'readwrite'

    def readable(self):
        return self == PropertyAccess.READ or self == PropertyAccess.READWRITE

    def writable(self):
        return self == PropertyAccess.WRITE or self == PropertyAccess.READWRITE


class ArgDirection(Enum):
    IN = 'in'
    OUT = 'out'


# http://man7.org/linux/man-pages/man3/sd-bus-errors.3.html
class ErrorType(Enum):
    SERVICE_ERROR = 'com.dubstepdish.dbus.next.ServiceError'
    INTERNAL_ERROR = 'com.dubstepdish.dbus.next.InternalError'
    CLIENT_ERROR = 'com.dubstepdish.dbus.next.ClientError'

    FAILED = "org.freedesktop.DBus.Error.Failed"
    NO_MEMORY = "org.freedesktop.DBus.Error.NoMemory"
    SERVICE_UNKNOWN = "org.freedesktop.DBus.Error.ServiceUnknown"
    NAME_HAS_NO_OWNER = "org.freedesktop.DBus.Error.NameHasNoOwner"
    NO_REPLY = "org.freedesktop.DBus.Error.NoReply"
    IO_ERROR = "org.freedesktop.DBus.Error.IOError"
    BAD_ADDRESS = "org.freedesktop.DBus.Error.BadAddress"
    NOT_SUPPORTED = "org.freedesktop.DBus.Error.NotSupported"
    LIMITS_EXCEEDED = "org.freedesktop.DBus.Error.LimitsExceeded"
    ACCESS_DENIED = "org.freedesktop.DBus.Error.AccessDenied"
    AUTH_FAILED = "org.freedesktop.DBus.Error.AuthFailed"
    NO_SERVER = "org.freedesktop.DBus.Error.NoServer"
    TIMEOUT = "org.freedesktop.DBus.Error.Timeout"
    NO_NETWORK = "org.freedesktop.DBus.Error.NoNetwork"
    ADDRESS_IN_USE = "org.freedesktop.DBus.Error.AddressInUse"
    DISCONNECTED = "org.freedesktop.DBus.Error.Disconnected"
    INVALID_ARGS = "org.freedesktop.DBus.Error.InvalidArgs"
    FILE_NOT_FOUND = "org.freedesktop.DBus.Error.FileNotFound"
    FILE_EXISTS = "org.freedesktop.DBus.Error.FileExists"
    UNKNOWN_METHOD = "org.freedesktop.DBus.Error.UnknownMethod"
    UNKNOWN_OBJECT = "org.freedesktop.DBus.Error.UnknownObject"
    UNKNOWN_INTERFACE = "org.freedesktop.DBus.Error.UnknownInterface"
    UNKNOWN_PROPERTY = "org.freedesktop.DBus.Error.UnknownProperty"
    PROPERTY_READ_ONLY = "org.freedesktop.DBus.Error.PropertyReadOnly"
    UNIX_PROCESS_ID_UNKNOWN = "org.freedesktop.DBus.Error.UnixProcessIdUnknown"
    INVALID_SIGNATURE = "org.freedesktop.DBus.Error.InvalidSignature"
    INCONSISTENT_MESSAGE = "org.freedesktop.DBus.Error.InconsistentMessage"
    MATCH_RULE_NOT_FOUND = "org.freedesktop.DBus.Error.MatchRuleNotFound"
    MATCH_RULE_INVALID = "org.freedesktop.DBus.Error.MatchRuleInvalid"
    INTERACTIVE_AUTHORIZATION_REQUIRED = "org.freedesktop.DBus.Error.InteractiveAuthorizationRequired"
