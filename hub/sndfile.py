"""Ogg Vorbis files read and written with libsndfile, through ctypes.

libsndfile is already on every Linux machine the voice runs on: paplay (pulseaudio-utils) is built
on it. A Mac has none of its own; there it comes with the soundfile package. So the recorded samples of voices not downloaded yet (hub/samples/, played by the ▶ in the
settings window) need no Python package of their own. Mono, 16-bit samples in and out.
"""
from __future__ import annotations

import ctypes
import ctypes.util

SFM_READ, SFM_WRITE = 0x10, 0x20
SF_FORMAT_OGG, SF_FORMAT_VORBIS = 0x200000, 0x0060
SFC_SET_VBR_ENCODING_QUALITY = 0x1300


class _Info(ctypes.Structure):
    _fields_ = [("frames", ctypes.c_int64), ("samplerate", ctypes.c_int), ("channels", ctypes.c_int),
                ("format", ctypes.c_int), ("sections", ctypes.c_int), ("seekable", ctypes.c_int)]


_lib = None


def _bundled() -> str | None:
    """A Mac has no libsndfile of its own: the soundfile package's wheel carries one, which the
    installer puts in the environment there."""
    import glob
    import importlib.util
    spec = importlib.util.find_spec("_soundfile_data")
    folders = list(spec.submodule_search_locations or []) if spec else []
    found = [p for folder in folders for p in glob.glob(f"{folder}/libsndfile*")]
    return found[0] if found else None


def _sndfile():
    global _lib
    if _lib is None:
        name = ctypes.util.find_library("sndfile") or _bundled() or "libsndfile.so.1"
        lib = ctypes.CDLL(name)
        lib.sf_open.restype = ctypes.c_void_p
        lib.sf_open.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(_Info)]
        lib.sf_readf_short.restype = ctypes.c_int64
        lib.sf_readf_short.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int64]
        lib.sf_writef_short.restype = ctypes.c_int64
        lib.sf_writef_short.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int64]
        lib.sf_command.restype = ctypes.c_int
        lib.sf_command.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
        lib.sf_close.argtypes = [ctypes.c_void_p]
        lib.sf_strerror.restype = ctypes.c_char_p
        lib.sf_strerror.argtypes = [ctypes.c_void_p]
        _lib = lib
    return _lib


def read(path: str):
    """(samples as int16 numpy array, rate) of a mono sound file. OSError if it cannot be read."""
    import numpy as np

    lib, info = _sndfile(), _Info()
    handle = lib.sf_open(path.encode(), SFM_READ, ctypes.byref(info))
    if not handle:
        raise OSError(f"cannot read {path}: {lib.sf_strerror(None).decode(errors='replace')}")
    try:
        if info.channels != 1:
            raise OSError(f"{path} is not mono")
        samples = np.zeros(info.frames, dtype=np.int16)
        got = lib.sf_readf_short(handle, samples.ctypes.data, info.frames)
        return samples[:got], info.samplerate
    finally:
        lib.sf_close(handle)


def write_ogg(path: str, samples, rate: int, quality: float = 0.3) -> None:
    """Write mono int16 samples as Ogg Vorbis (`quality` 0 to 1; 0.3 keeps a voice clear at about
    5 KB a second)."""
    import numpy as np

    lib = _sndfile()
    data = np.ascontiguousarray(samples, dtype=np.int16)
    info = _Info(frames=0, samplerate=rate, channels=1, format=SF_FORMAT_OGG | SF_FORMAT_VORBIS)
    handle = lib.sf_open(path.encode(), SFM_WRITE, ctypes.byref(info))
    if not handle:
        raise OSError(f"cannot write {path}: {lib.sf_strerror(None).decode(errors='replace')}")
    try:
        q = ctypes.c_double(quality)
        lib.sf_command(handle, SFC_SET_VBR_ENCODING_QUALITY, ctypes.byref(q), ctypes.sizeof(q))
        lib.sf_writef_short(handle, data.ctypes.data, len(data))
    finally:
        lib.sf_close(handle)
