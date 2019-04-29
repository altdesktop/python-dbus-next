from .address import parse_address
from ..errors import InvalidAddressError, AuthError

import os
import socket


class Connection:
    def __init__(self, address):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM | socket.SOCK_NONBLOCK)
        self.stream = self.sock.makefile('rwb')
        self.fd = self.sock.fileno()
        self.address = parse_address(address)
        self.setup_socket()
        self.authorize_socket()

    def authorize_socket(self):
        def readline():
            buf = self.sock.recv(2)
            while buf[-2:] != b'\r\n':
                buf += self.sock.recv(1)
            return buf

        # TODO other auth methods
        hex_uid = str(os.getuid()).encode().hex()
        self.sock.sendall(f'\0AUTH EXTERNAL {hex_uid}\r\n'.encode())
        resp = readline()
        if resp[:2] != b'OK':
            raise AuthError(f'DBus authorization failed with response: "{resp}"')
        self.stream.write('BEGIN\r\n'.encode())

    def setup_socket(self):
        err = None

        for transport, options in self.address:
            filename = None

            if transport == 'unix':
                if 'path' in options:
                    filename = options['path']
                elif 'abstract' in options:
                    filename = f'\0{options["abstract"]}'
                else:
                    raise InvalidAddressError('got unix transport with unknown path specifier')
            else:
                raise InvalidAddressError(f'got unknown address transport: {transport}')

            try:
                self.sock.connect(filename)
                break
            except Exception as e:
                err = e

        if err:
            raise err
