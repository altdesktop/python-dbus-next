import re

bus_name_re = re.compile(r'^[A-Za-z_-][A-Za-z0-9_-]*$')
path_re = re.compile(r'^[A-Za-z0-9_]+$')
element_re = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


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
        if bus_name_re.search(element) is None:
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
        if path_re.search(element) is None:
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
        if element_re.search(element) is None:
            return False

    return True


def is_member_name_valid(name):
    if not isinstance(name, str):
        return False

    if not name or len(name) > 255:
        return False

    if element_re.search(name) is None:
        return False

    return True


class InvalidBusNameError(TypeError):
    def __init__(self, name):
        super(f'invalid bus name: {name}')


def assert_bus_name_valid(name):
    if not is_bus_name_valid(name):
        raise InvalidBusNameError(name)


class InvalidObjectPathError(TypeError):
    def __init__(self, path):
        super(f'invalid object path: {path}')


def assert_object_path_valid(path):
    if not is_object_path_valid(path):
        raise InvalidObjectPathError(path)


class InvalidInterfaceNameError(TypeError):
    def __init__(self, name):
        super(f'invalid interface name: {name}')


def assert_interface_name_valid(name):
    if not is_interface_name_valid(name):
        raise InvalidInterfaceNameError(name)


class InvalidMemberNameError(TypeError):
    def __init__(self, member):
        super(f'invalid member name: {member}')


def assert_member_name_valid(member):
    if not is_member_name_valid(member):
        raise InvalidMemberNameError(member)
