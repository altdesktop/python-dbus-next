from ..proxy_object import BaseProxyObject, BaseProxyInterface
from ..message import Message
from ..errors import DBusError
from ..variant import Variant
from ..constants import ErrorType

# glib is optional
try:
    from gi.repository import GLib
except ImportError:
    pass


class ProxyInterface(BaseProxyInterface):
    def _add_method(self, intr_method):
        in_len = len(intr_method.in_args)
        out_len = len(intr_method.out_args)

        def method_fn(*args):
            if len(args) != in_len + 1:
                raise TypeError(
                    f'method {intr_method.name} expects {in_len} arguments and a callback (got {len(args)} args)'
                )

            args = list(args)
            # TODO type check: this callback takes two parameters
            # (MessageBus.check_callback(cb))
            callback = args.pop()

            def call_notify(msg, err):
                if err:
                    callback([], err)

                try:
                    BaseProxyInterface._check_method_return(msg, intr_method.out_signature)
                except DBusError as e:
                    err = e

                callback(msg.body, err)

            self.bus.call(
                Message(destination=self.bus_name,
                        path=self.path,
                        interface=self.introspection.name,
                        member=intr_method.name,
                        signature=intr_method.in_signature,
                        body=list(args)), call_notify)

        def method_fn_sync(*args):
            main = GLib.MainLoop()
            call_error = None
            call_body = None

            def callback(body, err):
                nonlocal call_error
                nonlocal call_body
                call_error = err
                call_body = body
                main.quit()

            method_fn(*args, callback)

            main.run()

            if call_error:
                raise call_error

            if not out_len:
                return None
            elif out_len == 1:
                return call_body[0]
            else:
                return call_body

        method_name = f'call_{BaseProxyInterface._to_snake_case(intr_method.name)}'
        method_name_sync = f'{method_name}_sync'

        setattr(self, method_name, method_fn)
        setattr(self, method_name_sync, method_fn_sync)

    def _add_property(self, intr_property):
        def property_getter(callback):
            def call_notify(msg, err):
                if err:
                    callback(None, err)
                    return

                try:
                    BaseProxyInterface._check_method_return(msg)
                except Exception as e:
                    callback(None, e)
                    return

                variant = msg.body[0]
                if variant.signature != intr_property.signature:
                    err = DBusError(ErrorType.CLIENT_ERROR,
                                    'property returned unexpected signature "{variant.signature}"',
                                    msg)
                    callback(None, err)
                    return

                callback(variant.value, None)

            self.bus.call(
                Message(destination=self.bus_name,
                        path=self.path,
                        interface='org.freedesktop.DBus.Properties',
                        member='Get',
                        signature='ss',
                        body=[self.introspection.name, intr_property.name]), call_notify)

        def property_getter_sync():
            property_value = None
            reply_error = None

            main = GLib.MainLoop()

            def callback(value, err):
                nonlocal property_value
                nonlocal reply_error
                property_value = value
                reply_error = err
                main.quit()

            property_getter(callback)
            main.run()
            if reply_error:
                raise reply_error
            return property_value

        def property_setter(value, callback):
            def call_notify(msg, err):
                if err:
                    callback(None, err)
                    return
                try:
                    BaseProxyInterface._check_method_return(msg)
                except Exception as e:
                    callback(None, e)
                    return

                return callback(None, None)

            variant = Variant(intr_property.signature, value)
            self.bus.call(
                Message(destination=self.bus_name,
                        path=self.path,
                        interface='org.freedesktop.DBus.Properties',
                        member='Set',
                        signature='ssv',
                        body=[self.introspection.name, intr_property.name, variant]), call_notify)

        def property_setter_sync(val):
            reply_error = None

            main = GLib.MainLoop()

            def callback(value, err):
                nonlocal reply_error
                reply_error = err
                main.quit()

            property_setter(val, callback)
            main.run()
            if reply_error:
                raise reply_error
            return None

        snake_case = super()._to_snake_case(intr_property.name)
        setattr(self, f'get_{snake_case}', property_getter)
        setattr(self, f'get_{snake_case}_sync', property_getter_sync)
        setattr(self, f'set_{snake_case}', property_setter)
        setattr(self, f'set_{snake_case}_sync', property_setter_sync)


class ProxyObject(BaseProxyObject):
    def __init__(self, bus_name, path, introspection, bus):
        super().__init__(bus_name, path, introspection, bus, ProxyInterface)
