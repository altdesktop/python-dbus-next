class SignatureBodyMismatchError(ValueError):
    pass


class InvalidSignatureError(ValueError):
    pass


class InvalidAddressError(ValueError):
    pass


class AuthError(Exception):
    pass


class InvalidMessageError(ValueError):
    pass


class InvalidIntrospectionError(ValueError):
    pass


class InterfaceNotFoundError(Exception):
    pass


class SignalDisabledError(Exception):
    pass


class InvalidBusNameError(TypeError):
    def __init__(self, name):
        super().__init__(f'invalid bus name: {name}')


class InvalidObjectPathError(TypeError):
    def __init__(self, path):
        super().__init__(f'invalid object path: {path}')


class InvalidInterfaceNameError(TypeError):
    def __init__(self, name):
        super().__init__(f'invalid interface name: {name}')


class InvalidMemberNameError(TypeError):
    def __init__(self, member):
        super().__init__(f'invalid member name: {member}')


class AnnotationMismatchError(TypeError):
    def __init__(self, msg):
        super().__init__(f'In signal handler, there is, one or more, mismatch of arg annotation: {msg}')

from .message import Message
from .validators import assert_interface_name_valid
from .constants import ErrorType, MessageType


class DBusError(Exception):
    def __init__(self, type_, text, reply=None):
        super().__init__(text)

        if type(type_) is ErrorType:
            type_ = type_.value

        assert_interface_name_valid(type_)
        if reply is not None and type(reply) is not Message:
            raise TypeError('reply must be of type Message')

        self.type = type_
        self.text = text
        self.reply = reply

    @staticmethod
    def _from_message(msg):
        assert msg.message_type == MessageType.ERROR
        return DBusError(msg.error_name, msg.body[0], reply=msg)

    def _as_message(self, msg):
        return Message.new_error(msg, self.type, self.text)
