"""Same-boot elapsed time including sleep; never infer active AI working time."""

import ctypes
import hashlib
import hmac
import sys
import time
from pathlib import Path

from .models import ClockStamp


def stamp(key: bytes) -> ClockStamp:
    try:
        if sys.platform == "darwin":
            lib = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)

            class Timebase(ctypes.Structure):
                _fields_ = [("numer", ctypes.c_uint32), ("denom", ctypes.c_uint32)]

            info = Timebase()
            lib.mach_timebase_info.argtypes = [ctypes.POINTER(Timebase)]
            lib.mach_timebase_info.restype = ctypes.c_int
            if lib.mach_timebase_info(ctypes.byref(info)) != 0 or not info.denom:
                raise ValueError
            lib.mach_continuous_time.argtypes = []
            lib.mach_continuous_time.restype = ctypes.c_uint64
            milliseconds = lib.mach_continuous_time() * info.numer // info.denom // 1_000_000
            boot = ctypes.create_string_buffer(128)
            length = ctypes.c_size_t(len(boot))
            lib.sysctlbyname.argtypes = [
                ctypes.c_char_p,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_size_t),
                ctypes.c_void_p,
                ctypes.c_size_t,
            ]
            lib.sysctlbyname.restype = ctypes.c_int
            if lib.sysctlbyname(b"kern.bootsessionuuid", boot, ctypes.byref(length), None, 0) != 0:
                raise ValueError
            boot_id = boot.value
        elif sys.platform == "linux":
            milliseconds = time.clock_gettime_ns(time.CLOCK_BOOTTIME) // 1_000_000
            boot_id = Path("/proc/sys/kernel/random/boot_id").read_bytes().strip()
        else:
            raise ValueError
        if not 16 <= len(boot_id) <= 128:
            raise ValueError
        return ClockStamp(
            kind="continuous",
            milliseconds=milliseconds,
            boot_token=hmac.new(key, b"session-boot-v1\n" + boot_id, hashlib.sha256).hexdigest(),
        )
    except (OSError, ValueError, AttributeError):
        return ClockStamp(kind="unavailable", milliseconds=None, boot_token=None)
