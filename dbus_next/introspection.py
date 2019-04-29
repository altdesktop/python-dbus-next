from .constants import PropertyAccess, ArgDirection
from .signature import SignatureTree, SignatureType
from .validators import assert_member_name_valid, assert_interface_name_valid
from .errors import InvalidIntrospectionError

import xml.etree.ElementTree as ET

# https://dbus.freedesktop.org/doc/dbus-specification.html#introspection-format
# TODO annotations


class Arg:
    def __init__(self, signature, direction=None, name=None):
        if name is not None:
            assert_member_name_valid(name)

        type_ = None
        if type(signature) is SignatureType:
            type_ = signature
            signature = signature.signature
        else:
            tree = SignatureTree(signature)
            if len(tree.types) != 1:
                raise InvalidIntrospectionError(
                    f'an argument must have a single complete type. (has {len(tree.types)} types)')
            type_ = tree.types[0]

        self.type = type_
        self.signature = signature
        self.name = name
        self.direction = direction

    def from_xml(element, direction):
        name = element.attrib.get('name')
        signature = element.attrib.get('type')

        if not signature:
            raise InvalidIntrospectionError('a method argument must have a "type" attribute')

        return Arg(signature, direction, name)

    def to_xml(self):
        element = ET.Element('arg')
        if self.name:
            element.set('name', self.name)

        if self.direction:
            element.set('direction', self.direction.value)
        element.set('type', self.signature)

        return element


class Signal:
    def __init__(self, name, args=None):
        if name is not None:
            assert_member_name_valid(name)

        self.name = name
        self.args = args or []
        self.signature = ''.join(arg.signature for arg in self.args)

    def from_xml(element):
        name = element.attrib.get('name')
        if not name:
            raise InvalidIntrospectionError('signals must have a "name" attribute')

        args = []
        for child in element:
            if child.tag == 'arg':
                args.append(Arg.from_xml(child, ArgDirection.OUT))

        signal = Signal(name, args)

        return signal

    def to_xml(self):
        element = ET.Element('signal')
        element.set('name', self.name)

        for arg in self.args:
            element.append(arg.to_xml())

        return element


class Method:
    def __init__(self, name, in_args=[], out_args=[]):
        assert_member_name_valid(name)

        self.name = name
        self.in_args = in_args
        self.out_args = out_args
        self.in_signature = ''.join(arg.signature for arg in in_args)
        self.out_signature = ''.join(arg.signature for arg in out_args)

    def from_xml(element):
        name = element.attrib.get('name')
        if not name:
            raise InvalidIntrospectionError('interfaces must have a "name" attribute')

        in_args = []
        out_args = []

        for child in element:
            if child.tag == 'arg':
                direction = ArgDirection(child.attrib.get('direction', 'in'))
                arg = Arg.from_xml(child, direction)
                if direction == ArgDirection.IN:
                    in_args.append(arg)
                elif direction == ArgDirection.OUT:
                    out_args.append(arg)

        return Method(name, in_args, out_args)

    def to_xml(self):
        element = ET.Element('method')
        element.set('name', self.name)

        for arg in self.in_args:
            element.append(arg.to_xml())
        for arg in self.out_args:
            element.append(arg.to_xml())

        return element


class Property:
    def __init__(self, name, signature, access=PropertyAccess.READWRITE):
        assert_member_name_valid(name)

        tree = SignatureTree(signature)
        if len(tree.types) != 1:
            raise InvalidIntrospectionError(
                f'properties must have a single complete type. (has {len(tree.types)} types)')

        self.name = name
        self.signature = signature
        self.access = access
        self.type = tree.types[0]

    def from_xml(element):
        name = element.attrib.get('name')
        signature = element.attrib.get('type')
        access = PropertyAccess(element.attrib.get('access', 'readwrite'))

        if not name:
            raise InvalidIntrospectionError('properties must have a "name" attribute')
        if not signature:
            raise InvalidIntrospectionError('properties must have a "type" attribute')

        return Property(name, signature, access)

    def to_xml(self):
        element = ET.Element('property')
        element.set('name', self.name)
        element.set('type', self.signature)
        element.set('access', self.access.value)
        return element


class Interface:
    def __init__(self, name, methods=None, signals=None, properties=None):
        assert_interface_name_valid(name)

        self.name = name
        self.methods = methods if methods is not None else []
        self.signals = signals if signals is not None else []
        self.properties = properties if properties is not None else []

    def from_xml(element):
        name = element.attrib.get('name')
        if not name:
            raise InvalidIntrospectionError('interfaces must have a "name" attribute')

        interface = Interface(name)

        for child in element:
            if child.tag == 'method':
                interface.methods.append(Method.from_xml(child))
            elif child.tag == 'signal':
                interface.signals.append(Signal.from_xml(child))
            elif child.tag == 'property':
                interface.properties.append(Property.from_xml(child))

        return interface

    def to_xml(self):
        element = ET.Element('interface')
        element.set('name', self.name)

        for method in self.methods:
            element.append(method.to_xml())
        for signal in self.signals:
            element.append(signal.to_xml())
        for prop in self.properties:
            element.append(prop.to_xml())

        return element


class Node:
    def __init__(self, name=None, interfaces=None, is_root=True):
        if not is_root and not name:
            raise InvalidIntrospectionError('child nodes must have a "name" attribute')

        self.interfaces = interfaces if interfaces is not None else []
        self.nodes = []
        self.name = name
        self.is_root = is_root

    def from_xml(element, is_root=False):
        node = Node(element.attrib.get('name'), is_root=is_root)

        for child in element:
            if child.tag == 'interface':
                node.interfaces.append(Interface.from_xml(child))
            elif child.tag == 'node':
                node.nodes.append(Node.from_xml(child))

        return node

    @staticmethod
    def parse(data):
        element = ET.fromstring(data)
        if element.tag != 'node':
            raise InvalidIntrospectionError(
                'introspection data must have a "node" for the root element')

        return Node.from_xml(element, is_root=True)

    def to_xml(self):
        element = ET.Element('node')

        if self.name:
            element.set('name', self.name)

        for interface in self.interfaces:
            element.append(interface.to_xml())
        for node in self.nodes:
            element.append(node.to_xml())

        return element

    def tostring(self):
        header = '<!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"\n"http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">\n'

        def indent(elem, level=0):
            i = "\n" + level * "    "
            if len(elem):
                if not elem.text or not elem.text.strip():
                    elem.text = i + "  "
                if not elem.tail or not elem.tail.strip():
                    elem.tail = i
                for elem in elem:
                    indent(elem, level + 1)
                if not elem.tail or not elem.tail.strip():
                    elem.tail = i
            else:
                if level and (not elem.tail or not elem.tail.strip()):
                    elem.tail = i

        xml = self.to_xml()
        indent(xml)
        return header + ET.tostring(xml, encoding='unicode').rstrip()

    def default(name=None):
        return Node(name,
                    is_root=True,
                    interfaces=[
                        Interface('org.freedesktop.DBus.Introspectable',
                                  methods=[
                                      Method('Introspect',
                                             out_args=[Arg('s', ArgDirection.OUT, 'data')])
                                  ]),
                        Interface('org.freedesktop.DBus.Peer',
                                  methods=[
                                      Method('GetMachineId',
                                             out_args=[Arg('s', ArgDirection.OUT, 'machine_uuid')]),
                                      Method('Ping')
                                  ]),
                        Interface('org.freedesktop.DBus.Properties',
                                  methods=[
                                      Method('Get',
                                             in_args=[
                                                 Arg('s', ArgDirection.IN, 'interface_name'),
                                                 Arg('s', ArgDirection.IN, 'property_name')
                                             ],
                                             out_args=[Arg('v', ArgDirection.OUT, 'value')]),
                                      Method('Set',
                                             in_args=[
                                                 Arg('s', ArgDirection.IN, 'interface_name'),
                                                 Arg('s', ArgDirection.IN, 'property_name'),
                                                 Arg('v', ArgDirection.IN, 'value')
                                             ]),
                                      Method('GetAll',
                                             in_args=[Arg('s', ArgDirection.IN, 'interface_name')],
                                             out_args=[Arg('a{sv}', ArgDirection.OUT, 'props')])
                                  ],
                                  signals=[
                                      Signal('PropertiesChanged',
                                             args=[
                                                 Arg('s', ArgDirection.OUT, 'interface_name'),
                                                 Arg('a{sv}', ArgDirection.OUT,
                                                     'changed_properties'),
                                                 Arg('as', ArgDirection.OUT,
                                                     'invalidated_properties')
                                             ])
                                  ])
                    ])
