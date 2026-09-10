"""Windows user-scope DPAPI. Deliberately no plaintext fallback."""

import ctypes, sys
from ctypes import wintypes
from kajovokarty.domain.core import AppError


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(data):
    buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    return Blob(len(data), buf), buf


def _crypt(data, decrypt):
    if sys.platform != "win32":
        raise AppError(
            "DPAPI_UNAVAILABLE",
            "Tokeny lze bezpečně uložit pouze v uživatelském profilu Windows.",
        )
    source, sourcebuf = _blob(data)
    entropy, entropybuf = _blob(b"cz.kajovo.kajovokarty")
    target = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.restype = wintypes.BOOL
    if not function(
        ctypes.byref(source),
        None,
        ctypes.byref(entropy),
        None,
        None,
        1,
        ctypes.byref(target),
    ):
        raise AppError(
            "DPAPI_FAILED",
            "Windows nedokázal odemknout nebo chránit tokeny. Zadejte je znovu v Nastavení.",
        )
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.memset(target.data, 0, target.size)
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree(target.data)


def protect(data):
    return _crypt(data, False)


def unprotect(data):
    return _crypt(data, True)
