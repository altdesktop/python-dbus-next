_has_gi = None
skip_reason_no_gi = 'glib tests require python3-gi'


def check_gi_repository():
    global _has_gi
    if _has_gi is not None:
        return _has_gi
    try:
        from gi.repository import GLib
        _has_gi = True
        return _has_gi
    except ImportError:
        _has_gi = False
        return _has_gi


_has_annotated = False
import typing
if hasattr(typing, "Annotated"):
    from typing import Annotated
    _has_annotated = True
else:
    try:
        from typing_extensions import Annotated
        _has_annotated = True
    except ImportError:
        pass

skip_reason_no_typing_annotated = 'Annotated tests require python 3.9 or typing-extensions'


def check_annotated():
    global _has_annotated
    return _has_annotated
