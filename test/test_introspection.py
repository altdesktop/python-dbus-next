from dbus_next import introspection as intr, ArgDirection, PropertyAccess, SignatureType

import os

example_data = open(f'{os.path.dirname(__file__)}/data/introspection.xml', 'r').read()


def test_example_introspection_from_xml():
    node = intr.Node.parse(example_data)

    assert len(node.interfaces) == 1
    interface = node.interfaces[0]

    assert len(node.nodes) == 2
    assert len(interface.methods) == 3
    assert len(interface.signals) == 2
    assert len(interface.properties) == 1

    assert type(node.nodes[0]) is intr.Node
    assert node.nodes[0].name == 'child_of_sample_object'
    assert type(node.nodes[1]) is intr.Node
    assert node.nodes[1].name == 'another_child_of_sample_object'

    assert interface.name == 'com.example.SampleInterface0'

    frobate = interface.methods[0]
    assert type(frobate) is intr.Method
    assert frobate.name == 'Frobate'
    assert len(frobate.in_args) == 1
    assert len(frobate.out_args) == 2

    foo = frobate.in_args[0]
    assert type(foo) is intr.Arg
    assert foo.name == 'foo'
    assert foo.direction == ArgDirection.IN
    assert foo.signature == 'i'
    assert type(foo.type) is SignatureType
    assert foo.type.token == 'i'

    bar = frobate.out_args[0]
    assert type(bar) is intr.Arg
    assert bar.name == 'bar'
    assert bar.direction == ArgDirection.OUT
    assert bar.signature == 's'
    assert type(bar.type) is SignatureType
    assert bar.type.token == 's'

    prop = interface.properties[0]
    assert type(prop) is intr.Property
    assert prop.name == 'Bar'
    assert prop.signature == 'y'
    assert type(prop.type) is SignatureType
    assert prop.type.token == 'y'
    assert prop.access == PropertyAccess.WRITE

    changed = interface.signals[0]
    assert type(changed) is intr.Signal
    assert changed.name == 'Changed'
    assert len(changed.args) == 1
    new_value = changed.args[0]
    assert type(new_value) is intr.Arg
    assert new_value.name == 'new_value'
    assert new_value.signature == 'b'


def test_example_introspection_to_xml():
    node = intr.Node.parse(example_data)
    tree = node.to_xml()
    assert tree.tag == 'node'
    assert tree.attrib.get('name') == '/com/example/sample_object0'
    assert len(tree) == 3
    interface = tree[0]
    assert interface.tag == 'interface'
    assert interface.get('name') == 'com.example.SampleInterface0'
    assert len(interface) == 6
    method = interface[0]
    assert method.tag == 'method'
    assert method.get('name') == 'Frobate'
    # TODO annotations
    assert len(method) == 3

    arg = method[0]
    assert arg.tag == 'arg'
    assert arg.attrib.get('name') == 'foo'
    assert arg.attrib.get('type') == 'i'
    assert arg.attrib.get('direction') == 'in'

    signal = interface[3]
    assert signal.tag == 'signal'
    assert signal.attrib.get('name') == 'Changed'
    assert len(signal) == 1

    arg = signal[0]
    assert arg.tag == 'arg'
    assert arg.attrib.get('name') == 'new_value'
    assert arg.attrib.get('type') == 'b'

    signal = interface[4]
    assert signal.tag == 'signal'
    assert signal.attrib.get('name') == 'ChangedMulti'
    assert len(signal) == 2

    arg = signal[0]
    assert arg.tag == 'arg'
    assert arg.attrib.get('name') == 'new_value1'
    assert arg.attrib.get('type') == 'b'

    arg = signal[1]
    assert arg.tag == 'arg'
    assert arg.attrib.get('name') == 'new_value2'
    assert arg.attrib.get('type') == 'y'

    prop = interface[5]
    assert prop.attrib.get('name') == 'Bar'
    assert prop.attrib.get('type') == 'y'
    assert prop.attrib.get('access') == 'write'


def test_default_interfaces():
    # just make sure it doesn't throw
    default = intr.Node.default()
    assert type(default) is intr.Node
