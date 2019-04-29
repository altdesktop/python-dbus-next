from .constants import PropertyAccess
from .signature import SignatureTree, SignatureBodyMismatchError
from . import introspection as intr
from .message import Message
from .variant import Variant
from .errors import SignalDisabledError

from functools import wraps
import inspect


class _Method:
    def __init__(self, fn, name, disabled=False):
        in_signature = ''
        out_signature = ''

        inspection = inspect.signature(fn)

        in_args = []
        for i, param in enumerate(inspection.parameters.values()):
            if i == 0:
                # first is self
                continue
            if param.annotation is inspect.Signature.empty:
                raise ValueError(
                    'method parameters must specify the dbus type string as a return annotation string'
                )
            in_args.append(intr.Arg(param.annotation, intr.ArgDirection.IN, param.name))
            in_signature += param.annotation

        out_args = []
        if inspection.return_annotation is not inspect.Signature.empty:
            out_signature = inspection.return_annotation
            for type_ in SignatureTree(inspection.return_annotation).types:
                out_args.append(intr.Arg(type_, intr.ArgDirection.OUT))

        self.name = name
        self.fn = fn
        self.disabled = disabled
        self.introspection = intr.Method(name, in_args, out_args)
        self.in_signature = in_signature
        self.out_signature = out_signature
        self.in_signature_tree = SignatureTree(in_signature)
        self.out_signature_tree = SignatureTree(out_signature)


def method(name=None, disabled=False):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            fn(*args, **kwargs)

        fn_name = name if name else fn.__name__
        wrapped.__dict__['__DBUS_METHOD'] = _Method(fn, fn_name, disabled=disabled)

        return wrapped

    return decorator


class _Signal:
    def __init__(self, fn, name, disabled=False):
        inspection = inspect.signature(fn)

        args = []
        signature = ''
        signature_tree = None

        if inspection.return_annotation is not inspect.Signature.empty:
            signature = inspection.return_annotation
            signature_tree = SignatureTree(signature)
            for type_ in signature_tree.types:
                args.append(intr.Arg(type_, intr.ArgDirection.OUT))
        else:
            signature = ''
            signature_tree = SignatureTree('')

        self.signature = signature
        self.signature_tree = signature_tree
        self.name = name
        self.disabled = disabled
        self.introspection = intr.Signal(self.name, args)


def signal(name=None, disabled=False):
    def decorator(fn):
        fn_name = name if name else fn.__name__
        signal = _Signal(fn, fn_name, disabled)

        @wraps(fn)
        def wrapped(self, *args, **kwargs):
            if signal.disabled:
                raise SignalDisabledError('Tried to call a disabled signal')
            result = fn(self, *args, **kwargs)
            ServiceInterface._handle_signal(self, signal, result)
            return result

        wrapped.__dict__['__DBUS_SIGNAL'] = signal

        return wrapped

    return decorator


class _Property(property):
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
        return _Property(fn, options=options)

    return decorator


class ServiceInterface:
    def __init__(self, name):
        # TODO cannot be overridden by a dbus member
        self.name = name
        self.__methods = []
        self.__properties = []
        self.__signals = []
        self.__buses = set()

        for name, member in inspect.getmembers(type(self)):
            member_dict = getattr(member, '__dict__', {})
            if type(member) is _Property:
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
                assert type(method) is _Method
                self.__methods.append(method)
            elif '__DBUS_SIGNAL' in member_dict:
                signal = member_dict['__DBUS_SIGNAL']
                assert type(signal) is _Signal
                self.__signals.append(signal)

        # validate that writable properties have a setter
        for prop in self.__properties:
            if prop.access.writable() and prop.prop_setter is None:
                raise ValueError(f'property "{member.name}" is writable but does not have a setter')

    def emit_properties_changed(self, changed_properties, invalidated_properties):
        # TODO cannot be overridden by a dbus member
        variant_dict = {}

        for prop in ServiceInterface._get_properties(self):
            if prop.name in changed_properties:
                variant_dict[prop.name] = Variant(prop.signature, changed_properties[prop.name])

        body = [self.name, variant_dict, invalidated_properties]
        for bus in ServiceInterface._get_buses(self):
            bus._interface_signal_notify(self, 'org.freedesktop.DBus.Properties',
                                         'PropertiesChanged', 'sa{sv}as', body)

    def introspect(self):
        # TODO cannot be overridden by a dbus member
        return intr.Interface(self.name,
                              methods=[
                                  method.introspection
                                  for method in ServiceInterface._get_methods(self)
                                  if not method.disabled
                              ],
                              signals=[
                                  signal.introspection
                                  for signal in ServiceInterface._get_signals(self)
                                  if not signal.disabled
                              ],
                              properties=[
                                  prop.introspection
                                  for prop in ServiceInterface._get_properties(self)
                                  if not prop.disabled
                              ])

    @staticmethod
    def _add_bus(interface, bus):
        interface.__buses.add(bus)

    @staticmethod
    def _remove_bus(interface, bus):
        interface.__buses.remove(bus)

    @staticmethod
    def _get_buses(interface):
        return interface.__buses

    @staticmethod
    def _get_properties(interface):
        return interface.__properties

    @staticmethod
    def _get_methods(interface):
        return interface.__methods

    @staticmethod
    def _get_signals(interface):
        return interface.__signals

    @staticmethod
    def _handle_signal(interface, signal, body):
        out_len = len(signal.signature_tree.types)
        if body is None:
            body = []
        elif out_len == 0:
            raise SignatureBodyMismatchError('Signal was not expected to return an argument')
        elif out_len == 1:
            body = [body]
        elif type(body) is not list:
            raise SignatureBodyMismatchError('Expected signal to return a list of arguments')

        for bus in ServiceInterface._get_buses(interface):
            bus._interface_signal_notify(interface, interface.name, signal.name, signal.signature,
                                         body)

    @staticmethod
    def _make_method_handler(interface, method):
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
