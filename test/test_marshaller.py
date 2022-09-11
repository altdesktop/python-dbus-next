from typing import Any, Dict
from dbus_next._private.unmarshaller import Unmarshaller
from dbus_next import Message, Variant, SignatureTree, MessageType, MessageFlag

import json
import os
import io

import pytest


def print_buf(buf):
    i = 0
    while True:
        p = buf[i:i + 8]
        if not p:
            break
        print(p)
        i += 8


# these messages have been verified with another library
table = json.load(open(os.path.dirname(__file__) + "/data/messages.json"))


def json_to_message(message: Dict[str, Any]) -> Message:
    copy = dict(message)
    if "message_type" in copy:
        copy["message_type"] = MessageType(copy["message_type"])
    if "flags" in copy:
        copy["flags"] = MessageFlag(copy["flags"])

    return Message(**copy)


# variants are an object in the json
def replace_variants(type_, item):
    if type_.token == "v" and type(item) is not Variant:
        item = Variant(
            item["signature"],
            replace_variants(SignatureTree(item["signature"]).types[0], item["value"]),
        )
    elif type_.token == "a":
        for i, item_child in enumerate(item):
            if type_.children[0].token == "{":
                for k, v in item.items():
                    item[k] = replace_variants(type_.children[0].children[1], v)
            else:
                item[i] = replace_variants(type_.children[0], item_child)
    elif type_.token == "(":
        for i, item_child in enumerate(item):
            if type_.children[0].token == "{":
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
        message = json_to_message(item["message"])

        body = []
        for i, type_ in enumerate(message.signature_tree.types):
            body.append(replace_variants(type_, message.body[i]))
        message.body = body

        buf = message._marshall()
        data = bytes.fromhex(item["data"])

        if buf != data:
            print("message:")
            print(json_dump(item["message"]))
            print("")
            print("mine:")
            print_buf(bytes(buf))
            print("")
            print("theirs:")
            print_buf(data)

        assert buf == data


@pytest.mark.parametrize("unmarshall_table", (table, ))
def test_unmarshalling_with_table(unmarshall_table):
    for item in unmarshall_table:

        stream = io.BytesIO(bytes.fromhex(item["data"]))
        unmarshaller = Unmarshaller(stream)
        try:
            unmarshaller.unmarshall()
        except Exception as e:
            print("message failed to unmarshall:")
            print(json_dump(item["message"]))
            raise e

        message = json_to_message(item["message"])

        body = []
        for i, type_ in enumerate(message.signature_tree.types):
            body.append(replace_variants(type_, message.body[i]))
        message.body = body

        for attr in [
            "body",
            "signature",
            "message_type",
            "destination",
            "path",
            "interface",
            "member",
            "flags",
            "serial",
        ]:
            assert getattr(unmarshaller.message, attr) == getattr(
                message, attr
            ), f"attr doesnt match: {attr}"


def test_unmarshall_can_resume():
    """Verify resume works."""
    bluez_rssi_message = (
        "6c04010134000000e25389019500000001016f00250000002f6f72672f626c75657a2f686369302f6465"
        "765f30385f33415f46325f31455f32425f3631000000020173001f0000006f72672e667265656465736b"
        "746f702e444275732e50726f7065727469657300030173001100000050726f706572746965734368616e"
        "67656400000000000000080167000873617b73767d617300000007017300040000003a312e3400000000"
        "110000006f72672e626c75657a2e446576696365310000000e0000000000000004000000525353490001"
        "6e00a7ff000000000000"
    )
    message_bytes = bytes.fromhex(bluez_rssi_message)

    class SlowStream(io.IOBase):
        """A fake stream that will only give us one byte at a time."""

        def __init__(self):
            self.data = message_bytes
            self.pos = 0

        def read(self, n) -> bytes:
            data = self.data[self.pos:self.pos + 1]
            self.pos += 1
            return data

    stream = SlowStream()
    unmarshaller = Unmarshaller(stream)

    for _ in range(len(bluez_rssi_message)):
        if unmarshaller.unmarshall():
            break
    assert unmarshaller.message is not None


def test_ay_buffer():
    body = [bytes(10000)]
    msg = Message(path="/test", member="test", signature="ay", body=body)
    marshalled = msg._marshall()
    unmarshalled_msg = Unmarshaller(io.BytesIO(marshalled)).unmarshall()
    assert unmarshalled_msg.body[0] == body[0]
