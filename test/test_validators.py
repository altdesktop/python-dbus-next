from dbus_next import (is_bus_name_valid, is_object_path_valid, is_interface_name_valid,
                       is_member_name_valid)


def test_object_path_validator():
    valid_paths = ['/', '/foo', '/foo/bar', '/foo/bar/bat']
    invalid_paths = [
        None, {}, '', 'foo', 'foo/bar', '/foo/bar/', '/$/foo/bar', '/foo//bar', '/foo$bar/baz'
    ]

    for path in valid_paths:
        assert is_object_path_valid(path), f'path should be valid: "{path}"'
    for path in invalid_paths:
        assert not is_object_path_valid(path), f'path should be invalid: "{path}"'


def test_bus_name_validator():
    valid_names = [
        'foo.bar', 'foo.bar.bat', '_foo._bar', 'foo.bar69', 'foo.bar-69',
        'org.mpris.MediaPlayer2.google-play-desktop-player'
    ]
    invalid_names = [
        None, {}, '', '5foo.bar', 'foo.6bar', '.foo.bar', 'bar..baz', '$foo.bar', 'foo$.ba$r'
    ]

    for name in valid_names:
        assert is_bus_name_valid(name), f'bus name should be valid: "{name}"'
    for name in invalid_names:
        assert not is_bus_name_valid(name), f'bus name should be invalid: "{name}"'


def test_interface_name_validator():
    valid_names = ['foo.bar', 'foo.bar.bat', '_foo._bar', 'foo.bar69']
    invalid_names = [
        None, {}, '', '5foo.bar', 'foo.6bar', '.foo.bar', 'bar..baz', '$foo.bar', 'foo$.ba$r',
        'org.mpris.MediaPlayer2.google-play-desktop-player'
    ]

    for name in valid_names:
        assert is_interface_name_valid(name), f'interface name should be valid: "{name}"'
    for name in invalid_names:
        assert not is_interface_name_valid(name), f'interface name should be invalid: "{name}"'


def test_member_name_validator():
    valid_members = ['foo', 'FooBar', 'Bat_Baz69']
    invalid_members = [None, {}, '', 'foo.bar', '5foo', 'foo$bar']

    for member in valid_members:
        assert is_member_name_valid(member), f'member name should be valid: "{member}"'
    for member in invalid_members:
        assert not is_member_name_valid(member), f'member name should be invalid: "{member}"'
