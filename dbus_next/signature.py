from .validators import is_object_path_valid
from .variant import Variant
from .errors import InvalidSignatureError, SignatureBodyMismatchError


class SignatureType:
    parsable_tokens = 'ybnqiuxtdsogav({'

    def __init__(self, token):
        self.token = token
        self.children = []

    def __eq__(self, other):
        if type(other) is SignatureType:
            return self.signature == other.signature
        else:
            return super().__eq__(other)

    def _collapse(self):
        if self.token not in 'a({':
            return self.token

        signature = [self.token]

        for child in self.children:
            signature.append(child._collapse())

        if self.token == '(':
            signature.append(')')
        elif self.token == '{':
            signature.append('}')

        return ''.join(signature)

    @property
    def signature(self):
        return self._collapse()

    @staticmethod
    def _parse_next(signature):
        if not signature:
            return (None, '')

        token = signature[0]

        if token not in SignatureType.parsable_tokens:
            raise InvalidSignatureError(f'got unexpected token: "{token}"')

        # container types
        if token == 'a':
            self = SignatureType('a')
            (child, signature) = SignatureType._parse_next(signature[1:])
            if not child:
                raise InvalidSignatureError('missing type for array')
            self.children.append(child)
            return (self, signature)
        elif token == '(':
            self = SignatureType('(')
            signature = signature[1:]
            while True:
                (child, signature) = SignatureType._parse_next(signature)
                if not signature:
                    raise InvalidSignatureError('missing closing ")" for struct')
                self.children.append(child)
                if signature[0] == ')':
                    return (self, signature[1:])
        elif token == '{':
            self = SignatureType('{')
            signature = signature[1:]
            (key_child, signature) = SignatureType._parse_next(signature)
            if not key_child or len(key_child.children):
                raise InvalidSignatureError('expected a simple type for dict entry key')
            self.children.append(key_child)
            (value_child, signature) = SignatureType._parse_next(signature)
            if not value_child:
                raise InvalidSignatureError('expected a value for dict entry')
            if not signature or signature[0] != '}':
                raise InvalidSignatureError('missing closing "}" for dict entry')
            self.children.append(value_child)
            return (self, signature[1:])

        # basic type
        return (SignatureType(token), signature[1:])

    def _verify_byte(self, body):
        BYTE_MIN = 0x00
        BYTE_MAX = 0xff
        if not isinstance(body, int):
            raise SignatureBodyMismatchError('DBus BYTE type "y" must be Python type "int"')
        if body < BYTE_MIN or body > BYTE_MAX:
            raise SignatureBodyMismatchError(
                f'DBus BYTE type must be between {BYTE_MIN} and {BYTE_MAX}')

    def _verify_boolean(self, body):
        if not isinstance(body, bool):
            raise SignatureBodyMismatchError('DBus BOOLEAN type "b" must be Python type "bool"')

    def _verify_int16(self, body):
        INT16_MIN = -0x7fff - 1
        INT16_MAX = 0x7fff
        if not isinstance(body, int):
            raise SignatureBodyMismatchError('DBus INT16 type "n" must be Python type "int"')
        elif body > INT16_MAX or body < INT16_MIN:
            raise SignatureBodyMismatchError(
                f'DBus INT16 type "n" must be between {INT16_MIN} and {INT16_MAX}')

    def _verify_uint16(self, body):
        UINT16_MIN = 0
        UINT16_MAX = 0xffff
        if not isinstance(body, int):
            raise SignatureBodyMismatchError('DBus UINT16 type "q" must be Python type "int"')
        elif body > UINT16_MAX or body < UINT16_MIN:
            raise SignatureBodyMismatchError(
                f'DBus UINT16 type "q" must be between {UINT16_MIN} and {UINT16_MAX}')

    def _verify_int32(self, body):
        INT32_MIN = -0x7fffffff - 1
        INT32_MAX = 0x7fffffff
        if not isinstance(body, int):
            raise SignatureBodyMismatchError('DBus INT32 type "i" must be Python type "int"')
        elif body > INT32_MAX or body < INT32_MIN:
            raise SignatureBodyMismatchError(
                f'DBus INT32 type "i" must be between {INT32_MIN} and {INT32_MAX}')

    def _verify_uint32(self, body):
        UINT32_MIN = 0
        UINT32_MAX = 0xffffffff
        if not isinstance(body, int):
            raise SignatureBodyMismatchError('DBus UINT32 type "u" must be Python type "int"')
        elif body > UINT32_MAX or body < UINT32_MIN:
            raise SignatureBodyMismatchError(
                f'DBus UINT32 type "u" must be between {UINT32_MIN} and {UINT32_MAX}')

    def _verify_int64(self, body):
        INT64_MAX = 9223372036854775807
        INT64_MIN = -INT64_MAX - 1
        if not isinstance(body, int):
            raise SignatureBodyMismatchError('DBus INT64 type "x" must be Python type "int"')
        elif body > INT64_MAX or body < INT64_MIN:
            raise SignatureBodyMismatchError(
                f'DBus INT64 type "x" must be between {INT64_MIN} and {INT64_MAX}')

    def _verify_uint64(self, body):
        UINT64_MIN = 0
        UINT64_MAX = 18446744073709551615
        if not isinstance(body, int):
            raise SignatureBodyMismatchError('DBus UINT64 type "t" must be Python type "int"')
        elif body > UINT64_MAX or body < UINT64_MIN:
            raise SignatureBodyMismatchError(
                f'DBus UINT64 type "t" must be between {UINT64_MIN} and {UINT64_MAX}')

    def _verify_double(self, body):
        if not isinstance(body, float) and not isinstance(body, int):
            raise SignatureBodyMismatchError(
                'DBus DOUBLE type "d" must be Python type "float" or "int"')

    def _verify_unix_fd(self, body):
        try:
            self._verify_uint32(body)
        except SignatureBodyMismatchError:
            raise SignatureBodyMismatchError('DBus UNIX_FD type "h" must be a valid UINT32')

    def _verify_object_path(self, body):
        if not is_object_path_valid(body):
            raise SignatureBodyMismatchError(
                'DBus OBJECT_PATH type "o" must be a valid object path')

    def _verify_string(self, body):
        if not isinstance(body, str):
            raise SignatureBodyMismatchError('DBus STRING type "s" must be Python type "str"')

    def _verify_signature(self, body):
        # I guess we could run it through the SignatureTree parser instead
        if not isinstance(body, str):
            raise SignatureBodyMismatchError('DBus SIGNATURE type "g" must be Python type "str"')
        if len(body.encode()) > 0xff:
            raise SignatureBodyMismatchError('DBus SIGNATURE type "g" must be less than 256 bytes')

    def _verify_array(self, body):
        child_type = self.children[0]

        if child_type.token == '{':
            if not isinstance(body, dict):
                raise SignatureBodyMismatchError(
                    'DBus ARRAY type "a" with DICT_ENTRY child must be Python type "dict"')
            for key, value in body.items():
                child_type.children[0].verify(key)
                child_type.children[1].verify(value)
        elif child_type.token == 'y':
            if not isinstance(body, bytes):
                raise SignatureBodyMismatchError(
                    'DBus ARRAY type "a" with BYTE child must be Python type "bytes"')
                # no need to verify children
        else:
            if not isinstance(body, list):
                raise SignatureBodyMismatchError('DBus ARRAY type "a" must be Python type "list"')
            for member in body:
                child_type.verify(member)

    def _verify_struct(self, body):
        # TODO allow tuples
        if not isinstance(body, list):
            raise SignatureBodyMismatchError('DBus STRUCT type "(" must be Python type "list"')

        if len(body) != len(self.children):
            raise SignatureBodyMismatchError(
                'DBus STRUCT type "(" must have Python list members equal to the number of struct type members'
            )

        for i, member in enumerate(body):
            self.children[i].verify(member)

    def _verify_variant(self, body):
        return
        # a variant signature and value is valid by construction
        if not isinstance(body, Variant):
            raise SignatureBodyMismatchError('DBus VARIANT type "v" must be Python type "Variant"')

    def verify(self, body):
        if body is None:
            raise SignatureBodyMismatchError('Cannot serialize Python type "None"')
        elif self.token == 'y':
            self._verify_byte(body)
        elif self.token == 'b':
            self._verify_boolean(body)
        elif self.token == 'n':
            self._verify_int16(body)
        elif self.token == 'q':
            self._verify_uint16(body)
        elif self.token == 'i':
            self._verify_int32(body)
        elif self.token == 'u':
            self._verify_uint32(body)
        elif self.token == 'x':
            self._verify_int64(body)
        elif self.token == 't':
            self._verify_uint64(body)
        elif self.token == 'd':
            self._verify_double(body)
        elif self.token == 'h':
            self._verify_unix_fd(body)
        elif self.token == 'o':
            self._verify_object_path(body)
        elif self.token == 's':
            self._verify_string(body)
        elif self.token == 'g':
            self._verify_signature(body)
        elif self.token == 'a':
            self._verify_array(body)
        elif self.token == '(':
            self._verify_struct(body)
        elif self.token == 'v':
            self._verify_variant(body)
        else:
            raise Exception(f'cannot verify type with token {self.token}')


class SignatureTree:
    def __init__(self, signature=''):
        self.signature = signature
        self.types = []

        if len(signature) > 0xff:
            raise InvalidSignatureError('A signature must be less than 256 characters')

        while signature:
            (type_, signature) = SignatureType._parse_next(signature)
            self.types.append(type_)

    def __eq__(self, other):
        if type(other) is SignatureTree:
            return self.signature == other.signature
        else:
            return super().__eq__(other)

    def verify(self, body):
        if not isinstance(body, list):
            raise SignatureBodyMismatchError(f'The body must be a list (got {type(body)})')
        if len(body) != len(self.types):
            raise SignatureBodyMismatchError(
                f'The body has the wrong number of types (got {len(body)}, expected {len(self.types)})'
            )
        for i, type_ in enumerate(self.types):
            type_.verify(body[i])
