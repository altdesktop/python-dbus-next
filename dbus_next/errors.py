from .validators import assert_interface_name_valid
from .message import Message
from .constants import ErrorType, MessageType

import traceback


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
    def from_message(msg):
        assert msg.message_type == MessageType.ERROR
        return DBusError(msg.error_name, msg.body[0], reply=msg)

    @staticmethod
    def internal_error(msg, text):
        return DBusError(ErrorType.INTERNAL_ERROR, f'{text}\n{traceback.format_exc()}')

    def as_message(self, msg):
        return Message.new_error(msg, self.type, self.text)
