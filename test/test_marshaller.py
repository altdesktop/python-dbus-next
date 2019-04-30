from dbus_next._private.unmarshaller import Unmarshaller
from dbus_next import Message, Variant, SignatureTree

import json
import os
import io


def print_buf(buf):
    i = 0
    while True:
        p = buf[i:i + 8]
        if not p:
            break
        print(p)
        i += 8


# these messages have been verified with another library
table = json.load(open(os.path.dirname(__file__) + '/data/messages.json'))


# variants are an object in the json
def replace_variants(type_, item):
    if type_.token == 'v' and type(item) is not Variant:
        item = Variant(item['signature'],
                       replace_variants(SignatureTree(item['signature']).types[0], item['value']))
    elif type_.token == 'a':
        for i, item_child in enumerate(item):
            if type_.children[0].token == '{':
                for k, v in item.items():
                    item[k] = replace_variants(type_.children[0].children[1], v)
            else:
                item[i] = replace_variants(type_.children[0], item_child)
    elif type_.token == '(':
        for i, item_child in enumerate(item):
            if type_.children[0].token == '{':
                assert False
            else:
                item[i] = replace_variants(type_.children[i], item_child)

    return item


def json_dump(what):
    def dumper(obj):
        try:
            return obj.toJSON()
        except Exception:
            return obj.__dict__

    return json.dumps(what, default=dumper, indent=2)


def test_marshalling_with_table():
    for item in table:
        message = Message(**item['message'])

        body = []
        for i, type_ in enumerate(message.signature_tree.types):
            body.append(replace_variants(type_, message.body[i]))
        message.body = body

        buf = message._marshall()
        data = bytes.fromhex(item['data'])

        if buf != data:
            print('message:')
            print(json_dump(item['message']))
            print('')
            print('mine:')
            print_buf(bytes(buf))
            print('')
            print('theirs:')
            print_buf(data)

        assert buf == data


def test_unmarshalling_with_table():
    for item in table:

        stream = io.BytesIO(bytes.fromhex(item['data']))
        unmarshaller = Unmarshaller(stream)
        try:
            unmarshaller.unmarshall()
        except Exception as e:
            print('message failed to unmarshall:')
            print(json_dump(item['message']))
            raise e

        message = Message(**item['message'])

        body = []
        for i, type_ in enumerate(message.signature_tree.types):
            body.append(replace_variants(type_, message.body[i]))
        message.body = body

        for attr in [
                'body', 'signature', 'message_type', 'destination', 'path', 'interface', 'member',
                'flags', 'serial'
        ]:
            assert getattr(unmarshaller.message,
                           attr) == getattr(message, attr), f'attr doesnt match: {attr}'


def test_ay_buffer():
    body = [bytes(10000)]
    msg = Message(path='/test', member='test', signature='ay', body=body)
    marshalled = msg._marshall()
    unmarshalled_msg = Unmarshaller(io.BytesIO(marshalled)).unmarshall()
    assert unmarshalled_msg.body[0] == body[0]
