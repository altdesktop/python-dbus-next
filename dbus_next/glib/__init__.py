from .message_bus import MessageBus
from .proxy_object import ProxyObject, ProxyInterface
from ..constants import BusType


def session_bus(bus_address=None, main_context=None, connect_notify=None):
    bus = MessageBus(bus_address=bus_address, bus_type=BusType.SESSION, main_context=main_context)
    bus.connect(connect_notify)
    return bus


def session_bus_sync(bus_address=None, main_context=None):
    return MessageBus(bus_address=bus_address, bus_type=BusType.SESSION,
                      main_context=main_context).connect_sync()


def system_bus(bus_address=None, main_context=None, connect_notify=None):
    bus = MessageBus(bus_address=bus_address, bus_type=BusType.SYSTEM, main_context=main_context)
    bus.connect(connect_notify)
    return bus


def system_bus_sync(bus_address=None, main_context=None):
    return MessageBus(bus_address=bus_address, bus_type=BusType.SYSTEM,
                      main_context=main_context).connect_sync()
