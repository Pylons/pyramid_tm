import sys

PY3 = sys.version_info[0] == 3

if PY3: # pragma: no cover
    import builtins
    exec_ = getattr(builtins, "exec")

    text_type = str
    binary_type = bytes

    def reraise(tp, value, tb=None):
        if value.__traceback__ is not tb:
            raise value.with_traceback(tb)
        raise value

else: # pragma: no cover
    def exec_(code, globs=None, locs=None):
        """Execute code in a namespace."""
        if globs is None:
            frame = sys._getframe(1)
            globs = frame.f_globals
            if locs is None:
                locs = frame.f_locals
            del frame
        elif locs is None:
            locs = globs
        exec("""exec code in globs, locs""")

    text_type = unicode
    binary_type = str

    exec_("""def reraise(tp, value, tb=None):
    raise tp, value, tb
""")
