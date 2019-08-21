from __future__ import annotations


class DBusException(Exception):
    pass


class SignatureBodyMismatchError(DBusException, ValueError):
    pass


class InvalidSignatureError(DBusException, ValueError):
    pass


class InvalidAddressError(DBusException, ValueError):
    pass


class AuthError(DBusException):
    pass


class InvalidMessageError(DBusException, ValueError):
    pass


class InvalidIntrospectionError(DBusException, ValueError):
    pass


class InterfaceNotFoundError(DBusException):
    pass


class SignalDisabledError(DBusException):
    pass


class InvalidBusNameError(DBusException, TypeError):
    def __init__(self, name):
        super().__init__(f'invalid bus name: {name}')


class InvalidObjectPathError(DBusException, TypeError):
    def __init__(self, path):
        super().__init__(f'invalid object path: {path}')


class InvalidInterfaceNameError(DBusException, TypeError):
    def __init__(self, name):
        super().__init__(f'invalid interface name: {name}')


class InvalidMemberNameError(DBusException, TypeError):
    def __init__(self, member):
        super().__init__(f'invalid member name: {member}')


from .message import Message
from .validators import assert_interface_name_valid
from .constants import ErrorType, MessageType


class DBusError(DBusException):
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
