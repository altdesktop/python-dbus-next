import os
import enum


class AuthResponse(enum.Enum):
    OK = 'OK'
    REJECTED = 'REJECTED'
    DATA = 'DATA'
    ERROR = 'ERROR'
    AGREE_UNIX_FD = 'AGREE_UNIX_FD'


def auth_external():
    hex_uid = str(os.getuid()).encode().hex()
    return f'AUTH EXTERNAL {hex_uid}\r\n'.encode()


def auth_begin():
    return b'BEGIN\r\n'


def auth_parse_line(line):
    args = line.decode().rstrip().split(' ')
    response = AuthResponse(args[0])
    return response, args[1:]
