from dbus_next import SignatureTree, SignatureBodyMismatchError, Variant
from dbus_next._private.util import signature_contains_type

import pytest


def assert_simple_type(signature, type_):
    assert type_.token == signature
    assert type_.signature == signature
    assert len(type_.children) == 0


def test_simple():
    tree = SignatureTree('s')
    assert len(tree.types) == 1
    assert_simple_type('s', tree.types[0])


def test_multiple_simple():
    tree = SignatureTree('sss')
    assert len(tree.types) == 3
    for i in range(0, 3):
        assert_simple_type('s', tree.types[i])


def test_array():
    tree = SignatureTree('as')
    assert len(tree.types) == 1
    child = tree.types[0]
    assert child.signature == 'as'
    assert child.token == 'a'
    assert len(child.children) == 1
    assert_simple_type('s', child.children[0])


def test_array_multiple():
    tree = SignatureTree('asasass')
    assert len(tree.types) == 4
    assert_simple_type('s', tree.types[3])
    for i in range(0, 3):
        array_child = tree.types[i]
        assert array_child.token == 'a'
        assert array_child.signature == 'as'
        assert len(array_child.children) == 1
        assert_simple_type('s', array_child.children[0])


def test_array_nested():
    tree = SignatureTree('aas')
    assert len(tree.types) == 1
    child = tree.types[0]
    assert child.token == 'a'
    assert child.signature == 'aas'
    assert len(child.children) == 1
    nested_child = child.children[0]
    assert nested_child.token == 'a'
    assert nested_child.signature == 'as'
    assert len(nested_child.children) == 1
    assert_simple_type('s', nested_child.children[0])


def test_simple_struct():
    tree = SignatureTree('(sss)')
    assert len(tree.types) == 1
    child = tree.types[0]
    assert child.signature == '(sss)'
    assert len(child.children) == 3
    for i in range(0, 3):
        assert_simple_type('s', child.children[i])


def test_nested_struct():
    tree = SignatureTree('(s(s(s)))')
    assert len(tree.types) == 1
    child = tree.types[0]
    assert child.signature == '(s(s(s)))'
    assert child.token == '('
    assert len(child.children) == 2
    assert_simple_type('s', child.children[0])
    first_nested = child.children[1]
    assert first_nested.token == '('
    assert first_nested.signature == '(s(s))'
    assert len(first_nested.children) == 2
    assert_simple_type('s', first_nested.children[0])
    second_nested = first_nested.children[1]
    assert second_nested.token == '('
    assert second_nested.signature == '(s)'
    assert len(second_nested.children) == 1
    assert_simple_type('s', second_nested.children[0])


def test_struct_multiple():
    tree = SignatureTree('(s)(s)(s)')
    assert len(tree.types) == 3
    for i in range(0, 3):
        child = tree.types[0]
        assert child.token == '('
        assert child.signature == '(s)'
        assert len(child.children) == 1
        assert_simple_type('s', child.children[0])


def test_array_of_structs():
    tree = SignatureTree('a(ss)')
    assert len(tree.types) == 1
    child = tree.types[0]
    assert child.token == 'a'
    assert child.signature == 'a(ss)'
    assert len(child.children) == 1
    struct_child = child.children[0]
    assert struct_child.token == '('
    assert struct_child.signature == '(ss)'
    assert len(struct_child.children) == 2
    for i in range(0, 2):
        assert_simple_type('s', struct_child.children[i])


def test_dict_simple():
    tree = SignatureTree('a{ss}')
    assert len(tree.types) == 1
    child = tree.types[0]
    assert child.signature == 'a{ss}'
    assert child.token == 'a'
    assert len(child.children) == 1
    dict_child = child.children[0]
    assert dict_child.token == '{'
    assert dict_child.signature == '{ss}'
    assert len(dict_child.children) == 2
    assert_simple_type('s', dict_child.children[0])
    assert_simple_type('s', dict_child.children[1])


def test_dict_of_structs():
    tree = SignatureTree('a{s(ss)}')
    assert len(tree.types) == 1
    child = tree.types[0]
    assert child.token == 'a'
    assert child.signature == 'a{s(ss)}'
    assert len(child.children) == 1
    dict_child = child.children[0]
    assert dict_child.token == '{'
    assert dict_child.signature == '{s(ss)}'
    assert len(dict_child.children) == 2
    assert_simple_type('s', dict_child.children[0])
    struct_child = dict_child.children[1]
    assert struct_child.token == '('
    assert struct_child.signature == '(ss)'
    assert len(struct_child.children) == 2
    for i in range(0, 2):
        assert_simple_type('s', struct_child.children[i])


def test_contains_type():
    tree = SignatureTree('h')
    assert signature_contains_type(tree, [0], 'h')
    assert not signature_contains_type(tree, [0], 'u')

    tree = SignatureTree('ah')
    assert signature_contains_type(tree, [[0]], 'h')
    assert signature_contains_type(tree, [[0]], 'a')
    assert not signature_contains_type(tree, [[0]], 'u')

    tree = SignatureTree('av')
    body = [[Variant('u', 0), Variant('i', 0), Variant('x', 0), Variant('v', Variant('s', 'hi'))]]
    assert signature_contains_type(tree, body, 'u')
    assert signature_contains_type(tree, body, 'x')
    assert signature_contains_type(tree, body, 'v')
    assert signature_contains_type(tree, body, 's')
    assert not signature_contains_type(tree, body, 'o')

    tree = SignatureTree('a{sv}')
    body = {
        'foo': Variant('h', 0),
        'bar': Variant('i', 0),
        'bat': Variant('x', 0),
        'baz': Variant('v', Variant('o', '/hi'))
    }
    for expected in 'hixvso':
        assert signature_contains_type(tree, [body], expected)
    assert not signature_contains_type(tree, [body], 'b')


def test_invalid_variants():
    tree = SignatureTree('a{sa{sv}}')
    s_con = {
        'type': '802-11-wireless',
        'uuid': '1234',
        'id': 'SSID',
    }

    s_wifi = {
        'ssid': 'SSID',
        'mode': 'infrastructure',
        'hidden': True,
    }

    s_wsec = {
        'key-mgmt': 'wpa-psk',
        'auth-alg': 'open',
        'psk': 'PASSWORD',
    }

    s_ip4 = {'method': 'auto'}
    s_ip6 = {'method': 'auto'}

    con = {
        'connection': s_con,
        '802-11-wireless': s_wifi,
        '802-11-wireless-security': s_wsec,
        'ipv4': s_ip4,
        'ipv6': s_ip6
    }

    with pytest.raises(SignatureBodyMismatchError):
        tree.verify([con])
