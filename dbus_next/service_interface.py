from .constants import PropertyAccess
from .signature import SignatureTree, SignatureBodyMismatchError
from . import introspection as intr
from .message import Message
from .variant import Variant

from functools import wraps
import inspect


class SignalDisabledError(Exception):
    pass


class Method:
    def __init__(self, fn, name, disabled=False):
        self.fn = fn
        self.name = name
        self.disabled = disabled
        self.in_signature = ''
        self.out_signature = ''

        inspection = inspect.signature(fn)

        in_args = []
        for i, (name, param) in enumerate(inspection.parameters.items()):
            if i == 0:
                # first is self
                continue
            if param.annotation is inspect.Signature.empty:
                raise ValueError(
                    'method parameters must specify the dbus type string as a return annotation string'
                )
            in_args.append(intr.Arg(param.annotation, intr.ArgDirection.IN, param.name))
            self.in_signature += param.annotation

        out_args = []
        if inspection.return_annotation is not inspect.Signature.empty:
            self.out_signature = inspection.return_annotation
            for type_ in SignatureTree(inspection.return_annotation).types:
                out_args.append(intr.Arg(type_, intr.ArgDirection.OUT))

        self.introspection = intr.Method(self.name, in_args, out_args)

        self.in_signature_tree = SignatureTree(self.in_signature)
        self.out_signature_tree = SignatureTree(self.out_signature)


def method(name=None, disabled=False):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            fn(*args, **kwargs)

        fn_name = name if name else fn.__name__
        wrapped.__dict__['__DBUS_METHOD'] = Method(fn, fn_name, disabled=disabled)

        return wrapped

    return decorator


class Signal:
    def __init__(self, fn, name, disabled=False):
        self.name = name
        self.disabled = disabled

        inspection = inspect.signature(fn)

        args = []
        if inspection.return_annotation is not inspect.Signature.empty:
            self.signature = inspection.return_annotation
            self.signature_tree = SignatureTree(self.signature)
            for type_ in self.signature_tree.types:
                args.append(intr.Arg(type_, intr.ArgDirection.OUT))
        else:
            self.signature = ''
            self.signature_tree = SignatureTree('')

        self.introspection = intr.Signal(self.name, args)


def signal(name=None, disabled=False):
    def decorator(fn):
        fn_name = name if name else fn.__name__
        signal = Signal(fn, fn_name, disabled)

        @wraps(fn)
        def wrapped(self, *args, **kwargs):
            if signal.disabled:
                raise SignalDisabledError('Tried to call a disabled signal')
            result = fn(self, *args, **kwargs)
            ServiceInterface.handle_signal(self, signal, result)
            return result

        wrapped.__dict__['__DBUS_SIGNAL'] = signal

        return wrapped

    return decorator


class Property(property):
    def set_options(self, options):
        self.options = getattr(self, 'options', {})
        for k, v in options.items():
            self.options[k] = v

        if 'name' in options and options['name'] is not None:
            self.name = options['name']
        else:
            self.name = self.prop_getter.__name__

        if 'access' in options:
            self.access = PropertyAccess(options['access'])
        else:
            self.access = PropertyAccess.READWRITE

        if 'disabled' in options:
            self.disabled = options['disabled']
        else:
            self.disabled = False

        self.introspection = intr.Property(self.name, self.signature, self.access)

        self.__dict__['__DBUS_PROPERTY'] = True

    def __init__(self, fn, *args, **kwargs):
        self.prop_getter = fn
        self.prop_setter = None

        sig = inspect.signature(fn)
        if len(sig.parameters) != 1:
            raise ValueError('the property must only have the "self" input parameter')

        if sig.return_annotation is inspect.Signature.empty:
            raise ValueError(
                'the property must specify the dbus type string as a return annotation string')

        self.signature = sig.return_annotation
        tree = SignatureTree(sig.return_annotation)

        if len(tree.types) != 1:
            raise ValueError('the property signature must be a single complete type')

        self.type = tree.types[0]

        if 'options' in kwargs:
            options = kwargs['options']
            self.set_options(options)
            del kwargs['options']

        super().__init__(fn, *args, **kwargs)

    def setter(self, fn, **kwargs):
        # XXX The setter decorator seems to be recreating the class in the list
        # of class members and clobbering the options so we need to reset them.
        # Why does it do that?
        result = super().setter(fn, **kwargs)
        result.prop_setter = fn
        result.set_options(self.options)
        return result


def dbus_property(access=PropertyAccess.READWRITE, name=None, disabled=False):
    def decorator(fn):
        options = {'name': name, 'access': access, 'disabled': disabled}
        return Property(fn, options=options)

    return decorator


class ServiceInterface:
    def __init__(self, name):
        self.name = name

        self.__methods = []
        self.__properties = []
        self.__signals = []
        self.__buses = set()

        for name, member in inspect.getmembers(type(self)):
            member_dict = getattr(member, '__dict__', {})
            if type(member) is Property:
                # XXX The getter and the setter may show up as different
                # members if they have different names. But if they have the
                # same name, they will be the same member. So we try to merge
                # them together here. I wish we could make this cleaner.
                found = False
                for prop in self.__properties:
                    if prop.prop_getter is member.prop_getter:
                        found = True
                        if member.prop_setter is not None:
                            prop.prop_setter = member.prop_setter

                if not found:
                    self.__properties.append(member)
            elif '__DBUS_METHOD' in member_dict:
                method = member_dict['__DBUS_METHOD']
                assert type(method) is Method
                self.__methods.append(method)
            elif '__DBUS_SIGNAL' in member_dict:
                signal = member_dict['__DBUS_SIGNAL']
                assert type(signal) is Signal
                self.__signals.append(signal)

        # validate that writable properties have a setter
        for prop in self.__properties:
            if prop.access.writable() and prop.prop_setter is None:
                raise ValueError(f'property "{member.name}" is writable but does not have a setter')

    @staticmethod
    def emit_properties_changed(interface, changed_properties, invalidated_properties):
        variant_dict = {}

        for prop in ServiceInterface.get_properties(interface):
            if prop.name in changed_properties:
                variant_dict[prop.name] = Variant(prop.signature, changed_properties[prop.name])

        body = [interface.name, variant_dict, invalidated_properties]
        for bus in interface.get_buses(interface):
            bus.interface_signal_notify(interface, 'org.freedesktop.DBus.Properties',
                                        'PropertiesChanged', 'sa{sv}as', body)

    @staticmethod
    def add_bus(interface, bus):
        interface.__buses.add(bus)

    @staticmethod
    def remove_bus(interface, bus):
        interface.__buses.remove(bus)

    @staticmethod
    def get_buses(interface):
        return interface.__buses

    @staticmethod
    def get_properties(interface):
        return interface.__properties

    @staticmethod
    def get_methods(interface):
        return interface.__methods

    @staticmethod
    def get_signals(interface):
        return interface.__signals

    @staticmethod
    def handle_signal(interface, signal, body):
        out_len = len(signal.signature_tree.types)
        if body is None:
            body = []
        elif out_len == 0:
            raise SignatureBodyMismatchError('Signal was not expected to return an argument')
        elif out_len == 1:
            body = [body]
        elif type(body) is not list:
            raise SignatureBodyMismatchError('Expected signal to return a list of arguments')

        for bus in ServiceInterface.get_buses(interface):
            bus.interface_signal_notify(interface, interface.name, signal.name, signal.signature,
                                        body)

    @staticmethod
    def make_method_handler(interface, method):
        def handler(msg):
            body = method.fn(interface, *msg.body)
            out_len = len(method.out_signature_tree.types)
            if body is None:
                body = []
            elif out_len == 0:
                raise SignatureBodyMismatchError('Method was not expected to return an argument')
            elif out_len == 1:
                body = [body]
            elif type(body) is not list:
                raise SignatureBodyMismatchError('Expected method to return a list of arguments')

            return Message.new_method_return(msg, method.out_signature, body)

        return handler

    def introspect(self):
        return intr.Interface(self.name,
                              methods=[
                                  method.introspection
                                  for method in ServiceInterface.get_methods(self)
                                  if not method.disabled
                              ],
                              signals=[
                                  signal.introspection
                                  for signal in ServiceInterface.get_signals(self)
                                  if not signal.disabled
                              ],
                              properties=[
                                  prop.introspection
                                  for prop in ServiceInterface.get_properties(self)
                                  if not prop.disabled
                              ])
