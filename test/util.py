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
