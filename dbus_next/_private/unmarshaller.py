from typing import Any, Callable, Dict, List, Optional, Tuple
from ..message import Message
from .constants import (
    HeaderField,
    LITTLE_ENDIAN,
    BIG_ENDIAN,
    PROTOCOL_VERSION,
)
from ..constants import MessageType, MessageFlag
from ..signature import SignatureTree, SignatureType, Variant
from ..errors import InvalidMessageError

import array
import io
import socket
import sys
from struct import Struct

MAX_UNIX_FDS = 16

UNPACK_SYMBOL = {LITTLE_ENDIAN: "<", BIG_ENDIAN: ">"}
UNPACK_LENGTHS = {BIG_ENDIAN: Struct(">III"), LITTLE_ENDIAN: Struct("<III")}
IS_BIG_ENDIAN = sys.byteorder == "big"
IS_LITTLE_ENDIAN = sys.byteorder == "little"

DBUS_TO_CTYPE = {
    "y": ("B", 1),  # byte
    "n": ("h", 2),  # int16
    "q": ("H", 2),  # uint16
    "i": ("i", 4),  # int32
    "u": ("I", 4),  # uint32
    "x": ("q", 8),  # int64
    "t": ("Q", 8),  # uint64
    "d": ("d", 8),  # double
    "h": ("I", 4),  # uint32
}

HEADER_SIGNATURE_SIZE = 16
HEADER_ARRAY_OF_STRUCT_SIGNATURE_POSITION = 12

UINT32_SIGNATURE = SignatureTree._get("u").types[0]

HEADER_DESTINATION = HeaderField.DESTINATION.name
HEADER_PATH = HeaderField.PATH.name
HEADER_INTERFACE = HeaderField.INTERFACE.name
HEADER_MEMBER = HeaderField.MEMBER.name
HEADER_ERROR_NAME = HeaderField.ERROR_NAME.name
HEADER_REPLY_SERIAL = HeaderField.REPLY_SERIAL.name
HEADER_SENDER = HeaderField.SENDER.name

READER_TYPE = Dict[str, Tuple[Optional[Callable[["Unmarshaller", SignatureType], Any]],
                              Optional[str], Optional[int], Optional[Struct], ], ]


class MarshallerStreamEndError(Exception):
    """This exception is raised when the end of the stream is reached.

    This means more data is expected on the wire that has not yet been
    received. The caller should call unmarshall later when more data is
    available.
    """

    pass


#
# Alignment padding is handled with the following formula below
#
# For any align value, the correct padding formula is:
#
#    (align - (offset % align)) % align
#
# However, if align is a power of 2 (always the case here), the slow MOD
# operator can be replaced by a bitwise AND:
#
#    (align - (offset & (align - 1))) & (align - 1)
#
# Which can be simplified to:
#
#    (-offset) & (align - 1)
#
#
class Unmarshaller:

    buf: bytearray
    view: memoryview
    message: Message
    unpack: Dict[str, Struct]
    readers: READER_TYPE

    def __init__(self, stream: io.BufferedRWPair, sock=None):
        self.unix_fds: List[int] = []
        self.can_cast = False
        self.buf = bytearray()  # Actual buffer
        self.view = None  # Memory view of the buffer
        self.offset = 0
        self.stream = stream
        self.sock = sock
        self.message = None
        self.readers = None
        self.body_len: int | None = None
        self.serial: int | None = None
        self.header_len: int | None = None
        self.message_type: MessageType | None = None
        self.flag: MessageFlag | None = None

    def read_sock(self, length: int) -> bytes:
        """reads from the socket, storing any fds sent and handling errors
        from the read itself"""
        unix_fd_list = array.array("i")

        try:
            msg, ancdata, *_ = self.sock.recvmsg(
                length, socket.CMSG_LEN(MAX_UNIX_FDS * unix_fd_list.itemsize))
        except BlockingIOError:
            raise MarshallerStreamEndError()

        for level, type_, data in ancdata:
            if not (level == socket.SOL_SOCKET and type_ == socket.SCM_RIGHTS):
                continue
            unix_fd_list.frombytes(data[:len(data) - (len(data) % unix_fd_list.itemsize)])
            self.unix_fds.extend(list(unix_fd_list))

        return msg

    def read_to_offset(self, offset: int) -> None:
        """
        Read from underlying socket into buffer.

        Raises MarshallerStreamEndError if there is not enough data to be read.

        :arg offset:
            The offset to read to. If not enough bytes are available in the
            buffer, read more from it.

        :returns:
            None
        """
        start_len = len(self.buf)
        missing_bytes = offset - (start_len - self.offset)
        if self.sock is None:
            data = self.stream.read(missing_bytes)
        else:
            data = self.read_sock(missing_bytes)
        if data == b"":
            raise EOFError()
        if data is None:
            raise MarshallerStreamEndError()
        self.buf.extend(data)
        if len(data) + start_len != offset:
            raise MarshallerStreamEndError()

    def read_boolean(self, _=None):
        return bool(self.read_argument(UINT32_SIGNATURE))

    def read_string(self, _=None):
        str_length = self.read_argument(UINT32_SIGNATURE)
        str_start = self.offset
        # read terminating '\0' byte as well (str_length + 1)
        self.offset += str_length + 1
        return self.buf[str_start:str_start + str_length].decode()

    def read_signature(self, _=None):
        signature_len = self.view[self.offset]  # byte
        o = self.offset + 1
        # read terminating '\0' byte as well (str_length + 1)
        self.offset = o + signature_len + 1
        return self.buf[o:o + signature_len].decode()

    def read_variant(self, _=None):
        tree = SignatureTree._get(self.read_signature())
        # verify in Variant is only useful on construction not unmarshalling
        return Variant(tree, self.read_argument(tree.types[0]), verify=False)

    def read_struct(self, type_: SignatureType):
        self.offset += -self.offset & 7  # align 8
        return [self.read_argument(child_type) for child_type in type_.children]

    def read_dict_entry(self, type_: SignatureType):
        self.offset += -self.offset & 7  # align 8
        return self.read_argument(type_.children[0]), self.read_argument(type_.children[1])

    def read_array(self, type_: SignatureType):
        self.offset += -self.offset & 3  # align 4 for the array
        array_length = self.read_argument(UINT32_SIGNATURE)

        child_type = type_.children[0]
        if child_type.token in "xtd{(":
            # the first alignment is not included in the array size
            self.offset += -self.offset & 7  # align 8

        if child_type.token == "y":
            self.offset += array_length
            return self.buf[self.offset - array_length:self.offset]

        beginning_offset = self.offset

        if child_type.token == "{":
            result_dict = {}
            while self.offset - beginning_offset < array_length:
                key, value = self.read_dict_entry(child_type)
                result_dict[key] = value
            return result_dict

        result_list = []
        while self.offset - beginning_offset < array_length:
            result_list.append(self.read_argument(child_type))
        return result_list

    def read_argument(self, type_: SignatureType) -> Any:
        """Dispatch to an argument reader or cast/unpack a C type."""
        token = type_.token
        reader, ctype, size, struct = self.readers[token]
        if reader:  # complex type
            return reader(self, type_)
        self.offset += size + (-self.offset & (size - 1))  # align
        if self.can_cast:
            return self.view[self.offset - size:self.offset].cast(ctype)[0]
        return struct.unpack_from(self.view, self.offset - size)[0]

    def header_fields(self, header_length):
        """Header fields are always a(yv)."""
        beginning_offset = self.offset
        headers = {}
        while self.offset - beginning_offset < header_length:
            # Now read the y (byte) of struct (yv)
            self.offset += (-self.offset & 7) + 1  # align 8 + 1 for 'y' byte
            field_0 = self.view[self.offset - 1]

            # Now read the v (variant) of struct (yv)
            signature_len = self.view[self.offset]  # byte
            o = self.offset + 1
            self.offset += signature_len + 2  # one for the byte, one for the '\0'
            tree = SignatureTree._get(self.buf[o:o + signature_len].decode())
            headers[HeaderField(field_0).name] = self.read_argument(tree.types[0])
        return headers

    def _read_header(self):
        """Read the header of the message."""
        # Signature is of the header is
        # BYTE, BYTE, BYTE, BYTE, UINT32, UINT32, ARRAY of STRUCT of (BYTE,VARIANT)
        self.read_to_offset(HEADER_SIGNATURE_SIZE)
        buffer = self.buf
        endian = buffer[0]
        self.message_type = MessageType(buffer[1])
        self.flag = MessageFlag(buffer[2])
        protocol_version = buffer[3]

        if endian != LITTLE_ENDIAN and endian != BIG_ENDIAN:
            raise InvalidMessageError(
                f"Expecting endianness as the first byte, got {endian} from {buffer}")
        if protocol_version != PROTOCOL_VERSION:
            raise InvalidMessageError(f"got unknown protocol version: {protocol_version}")

        self.body_len, self.serial, self.header_len = UNPACK_LENGTHS[endian].unpack_from(buffer, 4)
        self.msg_len = (self.header_len + (-self.header_len & 7) + self.body_len)  # align 8
        if IS_BIG_ENDIAN and endian == BIG_ENDIAN:
            self.can_cast = True
        elif IS_LITTLE_ENDIAN and endian == LITTLE_ENDIAN:
            self.can_cast = True
        self.readers = self._readers_by_type[endian]

    def _read_body(self):
        """Read the body of the message."""
        self.read_to_offset(HEADER_SIGNATURE_SIZE + self.msg_len)
        self.view = memoryview(self.buf)
        self.offset = HEADER_ARRAY_OF_STRUCT_SIGNATURE_POSITION
        header_fields = self.header_fields(self.header_len)
        self.offset += -self.offset & 7  # align 8
        tree = SignatureTree._get(header_fields.get(HeaderField.SIGNATURE.name, ""))
        self.message = Message(
            destination=header_fields.get(HEADER_DESTINATION),
            path=header_fields.get(HEADER_PATH),
            interface=header_fields.get(HEADER_INTERFACE),
            member=header_fields.get(HEADER_MEMBER),
            message_type=self.message_type,
            flags=self.flag,
            error_name=header_fields.get(HEADER_ERROR_NAME),
            reply_serial=header_fields.get(HEADER_REPLY_SERIAL),
            sender=header_fields.get(HEADER_SENDER),
            unix_fds=self.unix_fds,
            signature=tree.signature,
            body=[self.read_argument(t) for t in tree.types] if self.body_len else [],
            serial=self.serial,
        )

    def unmarshall(self):
        """Unmarshall the message.

        The underlying read function will raise MarshallerStreamEndError
        if there are not enough bytes in the buffer. This allows unmarshall
        to be resumed when more data comes in over the wire.
        """
        try:
            if not self.message_type:
                self._read_header()
            self._read_body()
        except MarshallerStreamEndError:
            return None
        return self.message

    _complex_parsers: Dict[str, Tuple[Callable[["Unmarshaller", SignatureType], Any], None, None,
                                      None]] = {
                                          "b": (read_boolean, None, None, None),
                                          "o": (read_string, None, None, None),
                                          "s": (read_string, None, None, None),
                                          "g": (read_signature, None, None, None),
                                          "a": (read_array, None, None, None),
                                          "(": (read_struct, None, None, None),
                                          "{": (read_dict_entry, None, None, None),
                                          "v": (read_variant, None, None, None),
                                      }

    _ctype_by_endian: Dict[int, Dict[str, Tuple[None, str, int, Struct]]] = {
        endian: {
            dbus_type: (
                None,
                *ctype_size,
                Struct(f"{UNPACK_SYMBOL[endian]}{ctype_size[0]}"),
            )
            for dbus_type, ctype_size in DBUS_TO_CTYPE.items()
        }
        for endian in (BIG_ENDIAN, LITTLE_ENDIAN)
    }

    _readers_by_type: Dict[int, READER_TYPE] = {
        BIG_ENDIAN: {
            **_ctype_by_endian[BIG_ENDIAN],
            **_complex_parsers
        },
        LITTLE_ENDIAN: {
            **_ctype_by_endian[LITTLE_ENDIAN],
            **_complex_parsers
        },
    }
