from dbus_next import PropertyAccess, introspection as intr
from dbus_next.service import ServiceInterface, method, signal, dbus_property


class ExampleInterface(ServiceInterface):
    def __init__(self):
        super().__init__('test.interface')
        self._some_prop = 55
        self._another_prop = 101
        self._weird_prop = 500

    @method()
    def some_method(self, one: 's', two: 's') -> 's':
        return 'hello'

    @method(name='renamed_method', disabled=True)
    def another_method(self, eight: 'o', six: 't'):
        pass

    @signal()
    def some_signal(self) -> 'as':
        return ['result']

    @signal(name='renamed_signal', disabled=True)
    def another_signal(self) -> '(dodo)':
        return [1, '/', 1, '/']

    @dbus_property(name='renamed_readonly_property', access=PropertyAccess.READ, disabled=True)
    def another_prop(self) -> 't':
        return self._another_prop

    @dbus_property()
    def some_prop(self) -> 'u':
        return self._some_prop

    @some_prop.setter
    def some_prop(self, val: 'u'):
        self._some_prop = val + 1

    # for this one, the setter has a different name than the getter which is a
    # special case in the code
    @dbus_property()
    def weird_prop(self) -> 't':
        return self._weird_prop

    @weird_prop.setter
    def setter_for_weird_prop(self, val: 't'):
        self._weird_prop = val


def test_method_decorator():
    interface = ExampleInterface()
    assert interface.name == 'test.interface'

    properties = ServiceInterface._get_properties(interface)
    methods = ServiceInterface._get_methods(interface)
    signals = ServiceInterface._get_signals(interface)

    assert len(methods) == 2

    method = methods[0]
    assert method.name == 'renamed_method'
    assert method.in_signature == 'ot'
    assert method.out_signature == ''
    assert method.disabled
    assert type(method.introspection) is intr.Method

    method = methods[1]
    assert method.name == 'some_method'
    assert method.in_signature == 'ss'
    assert method.out_signature == 's'
    assert not method.disabled
    assert type(method.introspection) is intr.Method

    assert len(signals) == 2

    signal = signals[0]
    assert signal.name == 'renamed_signal'
    assert signal.signature == '(dodo)'
    assert signal.disabled
    assert type(signal.introspection) is intr.Signal

    signal = signals[1]
    assert signal.name == 'some_signal'
    assert signal.signature == 'as'
    assert not signal.disabled
    assert type(signal.introspection) is intr.Signal

    assert len(properties) == 3

    renamed_readonly_prop = properties[0]
    assert renamed_readonly_prop.name == 'renamed_readonly_property'
    assert renamed_readonly_prop.signature == 't'
    assert renamed_readonly_prop.access == PropertyAccess.READ
    assert renamed_readonly_prop.disabled
    assert type(renamed_readonly_prop.introspection) is intr.Property

    weird_prop = properties[1]
    assert weird_prop.name == 'weird_prop'
    assert weird_prop.access == PropertyAccess.READWRITE
    assert weird_prop.signature == 't'
    assert not weird_prop.disabled
    assert weird_prop.prop_getter is not None
    assert weird_prop.prop_getter.__name__ == 'weird_prop'
    assert weird_prop.prop_setter is not None
    assert weird_prop.prop_setter.__name__ == 'setter_for_weird_prop'
    assert type(weird_prop.introspection) is intr.Property

    prop = properties[2]
    assert prop.name == 'some_prop'
    assert prop.access == PropertyAccess.READWRITE
    assert prop.signature == 'u'
    assert not prop.disabled
    assert prop.prop_getter is not None
    assert prop.prop_setter is not None
    assert type(prop.introspection) is intr.Property

    # make sure the getter and setter actually work
    assert interface._some_prop == 55
    interface._some_prop = 555
    assert interface.some_prop == 555

    assert interface._weird_prop == 500
    assert weird_prop.prop_getter(interface) == 500
    interface._weird_prop = 1001
    assert interface._weird_prop == 1001
    weird_prop.prop_setter(interface, 600)
    assert interface._weird_prop == 600


def test_interface_introspection():
    interface = ExampleInterface()
    intr_interface = interface.introspect()
    assert type(intr_interface) is intr.Interface

    xml = intr_interface.to_xml()

    assert xml.tag == 'interface'
    assert xml.attrib.get('name', None) == 'test.interface'

    methods = xml.findall('method')
    signals = xml.findall('signal')
    properties = xml.findall('property')

    assert len(xml) == 4
    assert len(methods) == 1
    assert len(signals) == 1
    assert len(properties) == 2
