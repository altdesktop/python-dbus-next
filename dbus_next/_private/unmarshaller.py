from ..message import Message
from .constants import HeaderField, LITTLE_ENDIAN, BIG_ENDIAN, PROTOCOL_VERSION
from ..constants import MessageType, MessageFlag
from ..signature import SignatureTree, Variant
from ..errors import InvalidMessageError

from struct import unpack


class MarshallerStreamEndError(Exception):
    pass


class Unmarshaller:
    def __init__(self, stream):
        self.buf = bytearray()
        self.offset = 0
        self.stream = stream
        self.endian = None
        self.message = None

        self.readers = {
            'y': self.read_byte,
            'b': self.read_boolean,
            'n': self.read_int16,
            'q': self.read_uint16,
            'i': self.read_int32,
            'u': self.read_uint32,
            'x': self.read_int64,
            't': self.read_uint64,
            'd': self.read_double,
            'h': self.read_uint32,
            'o': self.read_object_path,
            's': self.read_string,
            'g': self.read_signature,
            'a': self.read_array,
            '(': self.read_struct,
            '{': self.read_dict_entry,
            'v': self.read_variant
        }

    def read(self, n):
        # store previously read data in a buffer so we can resume on socket
        # interruptions
        data = bytearray()
        if self.offset < len(self.buf):
            data = self.buf[self.offset:self.offset + n]
            self.offset += len(data)
            n -= len(data)
        if n:
            read = self.stream.read(n)
            if read == b'':
                raise EOFError()
            elif read is None:
                raise MarshallerStreamEndError()
            data.extend(read)
            self.buf.extend(read)
            if len(read) != n:
                raise MarshallerStreamEndError()
        self.offset += n
        return bytes(data)

    def align(self, n):
        padding = n - self.offset % n
        if padding == 0 or padding == n:
            return b''
        return self.read(padding)

    def read_byte(self, _=None):
        return self.read(1)[0]

    def read_boolean(self, _=None):
        data = self.read_uint32()
        if data:
            return True
        else:
            return False

    def read_int16(self, _=None):
        self.align(2)
        fmt = '<h' if self.endian == LITTLE_ENDIAN else '>h'
        data = self.read(2)
        return unpack(fmt, data)[0]

    def read_uint16(self, _=None):
        self.align(2)
        fmt = '<H' if self.endian == LITTLE_ENDIAN else '>H'
        data = self.read(2)
        return unpack(fmt, data)[0]

    def read_int32(self, _=None):
        self.align(4)
        fmt = '<i' if self.endian == LITTLE_ENDIAN else '>i'
        data = self.read(4)
        return unpack(fmt, data)[0]

    def read_uint32(self, _=None):
        self.align(4)
        fmt = '<I' if self.endian == LITTLE_ENDIAN else '>I'
        data = self.read(4)
        return unpack(fmt, data)[0]

    def read_int64(self, _=None):
        self.align(8)
        fmt = '<q' if self.endian == LITTLE_ENDIAN else '>q'
        data = self.read(8)
        return unpack(fmt, data)[0]

    def read_uint64(self, _=None):
        self.align(8)
        fmt = '<Q' if self.endian == LITTLE_ENDIAN else '>Q'
        data = self.read(8)
        return unpack(fmt, data)[0]

    def read_double(self, _=None):
        self.align(8)
        fmt = '<d' if self.endian == LITTLE_ENDIAN else '>d'
        data = self.read(8)
        return unpack(fmt, data)[0]

    def read_object_path(self, _=None):
        path_length = self.read_uint32()
        data = self.read(path_length)
        self.read(1)
        return data.decode()

    def read_string(self, _=None):
        str_length = self.read_uint32()
        data = self.read(str_length)
        self.read(1)
        return data.decode()

    def read_signature(self, _=None):
        signature_len = self.read_byte()
        data = self.read(signature_len)
        self.read(1)
        return data.decode()

    def read_variant(self, _=None):
        signature = self.read_signature()
        signature_tree = SignatureTree(signature)
        value = self.read_argument(signature_tree.types[0])
        return Variant(signature_tree, value)

    def read_struct(self, type_):
        self.align(8)

        result = []
        for child_type in type_.children:
            result.append(self.read_argument(child_type))

        return result

    def read_dict_entry(self, type_):
        self.align(8)

        key = self.read_argument(type_.children[0])
        value = self.read_argument(type_.children[1])

        return key, value

    def read_array(self, type_):
        self.align(4)
        array_length = self.read_uint32()

        child_type = type_.children[0]
        if child_type.token in 'xtd{(':
            # the first alignment is not included in the array size
            self.align(8)

        beginning_offset = self.offset

        result = None
        if child_type.token == '{':
            result = {}
            while self.offset - beginning_offset < array_length:
                key, value = self.read_dict_entry(child_type)
                result[key] = value
        elif child_type.token == 'y':
            result = self.read(array_length)
        else:
            result = []
            while self.offset - beginning_offset < array_length:
                result.append(self.read_argument(child_type))

        return result

    def read_argument(self, type_):
        t = type_.token

        if t not in self.readers:
            raise Exception(f'dont know how to read yet: "{t}"')

        return self.readers[t](type_)

    def _unmarshall(self):
        self.offset = 0
        self.endian = self.read_byte()
        if self.endian != LITTLE_ENDIAN and self.endian != BIG_ENDIAN:
            raise InvalidMessageError('Expecting endianness as the first byte')
        message_type = MessageType(self.read_byte())
        flags = MessageFlag(self.read_byte())

        protocol_version = self.read_byte()

        if protocol_version != PROTOCOL_VERSION:
            raise InvalidMessageError(f'got unknown protocol version: {protocol_version}')

        body_len = self.read_uint32()
        serial = self.read_uint32()

        header_fields = {HeaderField.UNIX_FDS.name: []}
        for field_struct in self.read_argument(SignatureTree('a(yv)').types[0]):
            field = HeaderField(field_struct[0])
            if field == HeaderField.UNIX_FDS:
                header_fields[field.name].append(field_struct[1].value)
            else:
                header_fields[field.name] = field_struct[1].value

        self.align(8)

        path = header_fields.get(HeaderField.PATH.name)
        interface = header_fields.get(HeaderField.INTERFACE.name)
        member = header_fields.get(HeaderField.MEMBER.name)
        error_name = header_fields.get(HeaderField.ERROR_NAME.name)
        reply_serial = header_fields.get(HeaderField.REPLY_SERIAL.name)
        destination = header_fields.get(HeaderField.DESTINATION.name)
        sender = header_fields.get(HeaderField.SENDER.name)
        signature = header_fields.get(HeaderField.SIGNATURE.name, '')
        signature_tree = SignatureTree(signature)
        unix_fds = header_fields.get(HeaderField.UNIX_FDS.name)

        body = []

        if body_len:
            for type_ in signature_tree.types:
                body.append(self.read_argument(type_))

        self.message = Message(destination=destination,
                               path=path,
                               interface=interface,
                               member=member,
                               message_type=message_type,
                               flags=flags,
                               error_name=error_name,
                               reply_serial=reply_serial,
                               sender=sender,
                               unix_fds=unix_fds,
                               signature=signature_tree,
                               body=body,
                               serial=serial)

    def unmarshall(self):
        try:
            self._unmarshall()
            return self.message
        except MarshallerStreamEndError:
            return None
