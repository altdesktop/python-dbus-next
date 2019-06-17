#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/..'))

from dbus_next.validators import (is_bus_name_valid, is_member_name_valid, is_object_path_valid,
                                  is_interface_name_valid)
from dbus_next.aio import MessageBus
from dbus_next import MessageType, SignatureTree, BusType, Message, Variant
from argparse import ArgumentParser, OPTIONAL
import json

import asyncio

parser = ArgumentParser()

parser.add_argument('--system', help='Use the system bus', action='store_true')
parser.add_argument('--session', help='Use the session bus', action='store_true')
parser.add_argument('--dest', help='The destination address for the message', required=True)
parser.add_argument('--signature', help='The signature for the message body')
parser.add_argument('--type',
                    help='The type of message to send',
                    choices=[e.name for e in MessageType],
                    default=MessageType.METHOD_CALL.name,
                    nargs=OPTIONAL)
parser.add_argument('object_path', help='The object path for the message')
parser.add_argument('interface.member', help='The interface and member for the message')
parser.add_argument('body',
                    help='The JSON encoded body of the message. Must match the signature',
                    nargs=OPTIONAL)

args = parser.parse_args()


def exit_error(message):
    parser.print_usage()
    print()
    print(message)
    sys.exit(1)


interface_member = vars(args)['interface.member'].split('.')

if len(interface_member) < 2:
    exit_error(
        f'Expecting an interface and member separated by a dot: {vars(args)["interface.member"]}')

destination = args.dest
member = interface_member[-1]
interface = '.'.join(interface_member[:len(interface_member) - 1])
object_path = args.object_path
signature = args.signature
body = args.body
message_type = MessageType[args.type]
signature = args.signature

bus_type = BusType.SESSION

if args.system:
    bus_type = BusType.SYSTEM

if message_type is not MessageType.METHOD_CALL:
    exit_error('only message type METHOD_CALL is supported right now')

if not is_bus_name_valid(destination):
    exit_error(f'got invalid bus name: {destination}')

if not is_object_path_valid(object_path):
    exit_error(f'got invalid object path: {object_path}')

if not is_interface_name_valid(interface):
    exit_error(f'got invalid interface name: {interface}')

if not is_member_name_valid(member):
    exit_error(f'got invalid member name: {member}')

if body is None:
    body = []
    signature = ''
else:
    try:
        body = json.loads(body)
    except json.JSONDecodeError as e:
        exit_error(f'could not parse body as JSON: ({e})')

    if type(body) is not list:
        exit_error('body must be an array of arguments')

    if not signature:
        exit_error('--signature is a required argument when passing a message body')

loop = asyncio.get_event_loop()


async def main():
    bus = await MessageBus(bus_type=bus_type).connect()

    message = Message(destination=destination,
                      member=member,
                      interface=interface,
                      path=object_path,
                      signature=signature,
                      body=body)

    result = await bus.call(message)

    ret = 0

    if result.message_type is MessageType.ERROR:
        print(f'Error: {result.error_name}', file=sys.stderr)
        ret = 1

    def default(o):
        if type(o) is Variant:
            return [o.signature, o.value]
        else:
            raise json.JSONDecodeError()

    print(json.dumps(result.body, indent=2, default=default))

    sys.exit(ret)


loop.run_until_complete(main())
