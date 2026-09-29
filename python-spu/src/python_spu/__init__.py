"""Experimental contract-compatible SPU; no implicit network or deployment."""
import os as _os


def _open_descriptors():
    held = []
    for name in _os.listdir('/proc/self/fd'):
        fd = int(name)
        if fd <= 2:
            continue
        # listdir's enumeration descriptor is closed before probing each number.
        try:
            _os.fstat(fd)
        except OSError:
            continue
        held.append(fd)
    return sorted(held)


# The descriptors the process held when the package was first imported, before any
# module that opens one of its own. python-build-standalone's ctypes opens the
# interpreter's own executable at import, so a count taken at adoption, after the
# sampler and the transport have imported ctypes, would see it among the inherited.
INHERITED = _open_descriptors()
