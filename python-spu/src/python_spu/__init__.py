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

# **The SPU is one process: it starts no child**, per python-spu-Spec section 8, so what
# the import set and the maps rule judge is everything it runs. Two things started one.
# - transformers' loading progress bar made a tqdm, whose default write lock is a
#   multiprocessing RLock, and that semaphore's registration launches Python's
#   resource tracker, a second interpreter that outlives the load. With the bars off,
#   transformers uses its empty stand-in, so no lock is made, and the load writes no
#   bar to the unit's journal either.
# - ctypes.util.find_library runs /sbin/ldconfig, then gcc or ld where that fails, in a
#   subprocess, and cuda.pathfinder calls it at torch's import. It answers nothing here.
#   Every caller in the lock falls back or never runs: cuda.pathfinder to the stable
#   `libdl.so.2`, torch's inductor, a compile path this implementation never enters,
#   and pip's macOS truststore. The package's own libm is loaded by its soname.
_os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
import ctypes.util as _ctypes_util  # noqa: E402, after INHERITED, since ctypes opens a descriptor


def _find_library(name):
    return None


_ctypes_util.find_library = _find_library

# **The determinism environment is the SPU's own**, per python-spu-Spec section 8. The
# engine enables torch's deterministic algorithms, and cuBLAS then needs a fixed
# workspace, so it is set here, before torch can initialise CUDA, rather than left to a
# deployment line an admin configuration serving both SPUs may not carry. A value the
# environment already holds that differs is kept, and the entry refuses it by name: a
# deployment that set one meant it, and overwriting it silently would serve a
# determinism nobody wrote.
CUBLAS_WORKSPACE = ":4096:8"
CUBLAS_WORKSPACE_PRIOR = _os.environ.get("CUBLAS_WORKSPACE_CONFIG")
_os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", CUBLAS_WORKSPACE)
