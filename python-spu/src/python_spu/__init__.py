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

# **No runtime compilation, whatever the environment holds**, per python-spu-Spec
# section 8. torch's native DSL ops route some CUDA calls, an outer-product bmm among
# them, through kernels a DSL compiles at the first call, triton's by compiling its
# driver helper with the system's compiler. The lock carries no triton, and this
# turns the registration off before torch is imported, so a box whose environment
# gained triton still serves torch's eager kernels. Set here, at the package's first
# import, because the registration runs at torch's.
_os.environ["TORCH_DISABLE_NATIVE_JIT"] = "1"
