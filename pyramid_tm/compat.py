import sys

PY2 = sys.version_info[0] == 2

if PY2:
    text_type = unicode

    def exec_(_code_, _globs_=None, _locs_=None):
        """Execute code in a namespace."""
        if _globs_ is None:
            frame = sys._getframe(1)
            _globs_ = frame.f_globals
            if _locs_ is None:
                _locs_ = frame.f_locals
            del frame
        elif _locs_ is None:  # pragma: no cover
            _locs_ = _globs_
        exec("""exec _code_ in _globs_, _locs_""")

    exec_("""def reraise(tp, value, tb=None):
    try:
        raise tp, value, tb
    finally:
        tb = None
""")

else:
    text_type = str

    def reraise(tp, value, tb=None):
        try:
            if value is None:  # pragma: no cover
                value = tp()
            if value.__traceback__ is not tb:  # pragma: no cover
                raise value.with_traceback(tb)
            raise value
        finally:
            value = None
            tb = None

def text_(s):
    if isinstance(s, bytes):
        try:
            return s.decode('utf-8')
        except UnicodeDecodeError:
            return s.decode('latin-1')
    return text_type(s)
