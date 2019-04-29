import re
from .errors import InvalidBusNameError, InvalidObjectPathError, InvalidInterfaceNameError, InvalidMemberNameError

_bus_name_re = re.compile(r'^[A-Za-z_-][A-Za-z0-9_-]*$')
_path_re = re.compile(r'^[A-Za-z0-9_]+$')
_element_re = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def is_bus_name_valid(name):
    if not isinstance(name, str):
        return False

    if not name or len(name) > 255:
        return False

    if name.startswith(':'):
        # a unique bus name
        return True

    if name.startswith('.'):
        return False

    if name.find('.') == -1:
        return False

    for element in name.split('.'):
        if _bus_name_re.search(element) is None:
            return False

    return True


def is_object_path_valid(path):
    if not isinstance(path, str):
        return False

    if not path:
        return False

    if not path.startswith('/'):
        return False

    if len(path) == 1:
        return True

    for element in path[1:].split('/'):
        if _path_re.search(element) is None:
            return False

    return True


def is_interface_name_valid(name):
    if not isinstance(name, str):
        return False

    if not name or len(name) > 255:
        return False

    if name.startswith('.'):
        return False

    if name.find('.') == -1:
        return False

    for element in name.split('.'):
        if _element_re.search(element) is None:
            return False

    return True


def is_member_name_valid(name):
    if not isinstance(name, str):
        return False

    if not name or len(name) > 255:
        return False

    if _element_re.search(name) is None:
        return False

    return True


def assert_bus_name_valid(name):
    if not is_bus_name_valid(name):
        raise InvalidBusNameError(name)


def assert_object_path_valid(path):
    if not is_object_path_valid(path):
        raise InvalidObjectPathError(path)


def assert_interface_name_valid(name):
    if not is_interface_name_valid(name):
        raise InvalidInterfaceNameError(name)


def assert_member_name_valid(member):
    if not is_member_name_valid(member):
        raise InvalidMemberNameError(member)
