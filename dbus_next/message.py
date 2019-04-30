from ._private.marshaller import Marshaller
from .variant import Variant
from .constants import MessageType, MessageFlag, ErrorType
from ._private.constants import PROTOCOL_VERSION, HeaderField, LITTLE_ENDIAN
from .validators import is_bus_name_valid, is_member_name_valid, is_object_path_valid, is_interface_name_valid
from .errors import InvalidMessageError
from .signature import SignatureTree


class Message:
    def __init__(self,
                 destination=None,
                 path=None,
                 interface=None,
                 member=None,
                 message_type=MessageType.METHOD_CALL,
                 flags=MessageFlag.NONE,
                 error_name=None,
                 reply_serial=None,
                 sender=None,
                 unix_fds=[],
                 signature='',
                 body=[],
                 serial=0):
        self.destination = destination
        self.path = path
        self.interface = interface
        self.member = member
        self.message_type = message_type
        self.flags = flags if type(flags) is MessageFlag else MessageFlag(bytes([flags]))
        self.error_name = error_name if type(error_name) is not ErrorType else error_name.value
        self.reply_serial = reply_serial
        self.sender = sender
        self.unix_fds = unix_fds
        self.signature = signature.signature if type(signature) is SignatureTree else signature
        self.signature_tree = signature if type(signature) is SignatureTree else SignatureTree(
            signature)
        self.body = body
        self.serial = serial

        if self.destination and not is_bus_name_valid(self.destination):
            raise InvalidMessageError(f'invalid destination: {self.destination}')
        elif self.interface and not is_interface_name_valid(self.interface):
            raise InvalidMessageError(f'invalid interface name: {self.interface}')
        elif self.path and not is_object_path_valid(self.path):
            raise InvalidMessageError(f'invalid path: {self.path}')
        elif self.member and not is_member_name_valid(self.member):
            raise InvalidMessageError(f'invalid member: {self.member}')
        elif self.error_name and not is_interface_name_valid(self.error_name):
            raise InvalidMessageError(f'invalid error_name: {self.error_name}')

        def require_fields(*fields):
            for field in fields:
                if not getattr(self, field):
                    raise InvalidMessageError(f'missing required field: {field}')

        if self.message_type == MessageType.METHOD_CALL:
            require_fields('path', 'member')
        elif self.message_type == MessageType.SIGNAL:
            require_fields('path', 'member', 'interface')
        elif self.message_type == MessageType.ERROR:
            require_fields('error_name', 'reply_serial')
        elif self.message_type == MessageType.METHOD_RETURN:
            require_fields('reply_serial')
        else:
            raise InvalidMessageError(f'got unknown message type: {self.message_type}')

    @staticmethod
    def new_error(msg, error_name, error_text):
        return Message(message_type=MessageType.ERROR,
                       reply_serial=msg.serial,
                       destination=msg.sender,
                       error_name=error_name,
                       signature='s',
                       body=[error_text])

    @staticmethod
    def new_method_return(msg, signature='', body=[]):
        return Message(message_type=MessageType.METHOD_RETURN,
                       reply_serial=msg.serial,
                       destination=msg.sender,
                       signature=signature,
                       body=body)

    @staticmethod
    def new_signal(path, interface, member, signature='', body=None):
        body = body if body else []
        return Message(message_type=MessageType.SIGNAL,
                       interface=interface,
                       path=path,
                       member=member,
                       signature=signature,
                       body=body)

    def _matches(self, **kwargs):
        for attr, val in kwargs.items():
            if getattr(self, attr) != val:
                return False

        return True

    def _marshall(self):
        # TODO maximum message size is 134217728 (128 MiB)
        body_block = Marshaller(self.signature, self.body)
        body_block.marshall()

        fields = []

        if self.path:
            fields.append([HeaderField.PATH.value, Variant('o', self.path)])
        if self.interface:
            fields.append([HeaderField.INTERFACE.value, Variant('s', self.interface)])
        if self.member:
            fields.append([HeaderField.MEMBER.value, Variant('s', self.member)])
        if self.error_name:
            fields.append([HeaderField.ERROR_NAME.value, Variant('s', self.error_name)])
        if self.reply_serial:
            fields.append([HeaderField.REPLY_SERIAL.value, Variant('u', self.reply_serial)])
        if self.destination:
            fields.append([HeaderField.DESTINATION.value, Variant('s', self.destination)])
        if self.signature:
            fields.append([HeaderField.SIGNATURE.value, Variant('g', self.signature)])
        for fd in self.unix_fds:
            fields.append([HeaderField.UNIX_FDS.value, Variant('h', fd)])

        header_body = [
            LITTLE_ENDIAN, self.message_type.value, self.flags.value, PROTOCOL_VERSION,
            len(body_block.buffer), self.serial, fields
        ]
        header_block = Marshaller('yyyyuua(yv)', header_body)
        header_block.marshall()
        header_block.align(8)
        return header_block.buffer + body_block.buffer
