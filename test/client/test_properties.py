from dbus_next.aio.message_bus import MessageBus as AIOMessageBus
from dbus_next.glib.message_bus import MessageBus as GLibMessageBus
from dbus_next.service_interface import ServiceInterface, dbus_property
from dbus_next.errors import DBusError
from dbus_next.message import Message

import pytest


class ExampleInterface(ServiceInterface):
    def __init__(self):
        super().__init__('test.interface')
        self._some_property = 'foo'
        self.error_name = 'test.error'
        self.error_text = 'i am bad'

    @dbus_property()
    def SomeProperty(self) -> 's':
        return self._some_property

    @SomeProperty.setter
    def SomeProperty(self, val: 's'):
        self._some_property = val

    @dbus_property()
    def ErrorThrowingProperty(self) -> 's':
        raise DBusError(self.error_name, self.error_text)

    @ErrorThrowingProperty.setter
    def ErrorThrowingProperty(self, val: 's'):
        raise DBusError(self.error_name, self.error_text)


@pytest.mark.asyncio
async def test_aio_properties():
    service_bus = await AIOMessageBus().connect()
    service_interface = ExampleInterface()
    service_bus.export('/test/path', service_interface)

    bus = await AIOMessageBus().connect()
    obj = bus.get_proxy_object(service_bus.name, '/test/path',
                               service_bus.introspect_export_path('/test/path'))
    interface = obj.get_interface(service_interface.name)

    prop = await interface.get_some_property()
    assert prop == service_interface._some_property

    await interface.set_some_property('different')
    assert service_interface._some_property == 'different'

    with pytest.raises(DBusError):
        try:
            prop = await interface.get_error_throwing_property()
            assert False, prop
        except DBusError as e:
            assert e.type == service_interface.error_name
            assert e.text == service_interface.error_text
            assert type(e.reply) is Message
            raise e

    with pytest.raises(DBusError):
        try:
            await interface.set_error_throwing_property('different')
        except DBusError as e:
            assert e.type == service_interface.error_name
            assert e.text == service_interface.error_text
            assert type(e.reply) is Message
            raise e

    service_bus.disconnect()
    bus.disconnect()


def test_glib_properties():
    service_bus = GLibMessageBus().connect_sync()
    service_interface = ExampleInterface()
    service_bus.export('/test/path', service_interface)

    bus = GLibMessageBus().connect_sync()
    obj = bus.get_proxy_object(service_bus.name, '/test/path',
                               service_bus.introspect_export_path('/test/path'))
    interface = obj.get_interface(service_interface.name)

    prop = interface.get_some_property_sync()
    assert prop == service_interface._some_property

    interface.set_some_property_sync('different')
    assert service_interface._some_property == 'different'

    with pytest.raises(DBusError):
        try:
            prop = interface.get_error_throwing_property_sync()
            assert False, prop
        except DBusError as e:
            assert e.type == service_interface.error_name
            assert e.text == service_interface.error_text
            assert type(e.reply) is Message
            raise e

    with pytest.raises(DBusError):
        try:
            interface.set_error_throwing_property_sync('different2')
        except DBusError as e:
            assert e.type == service_interface.error_name
            assert e.text == service_interface.error_text
            assert type(e.reply) is Message
            raise e
