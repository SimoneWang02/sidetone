"""NVIDIA's libraries for running the speech models on the graphics card.

Whisper (ctranslate2) and the voice (onnxruntime-gpu) open NVIDIA's CUDA libraries by name only
when a model goes on the card. They come as pip packages in the hub's environment (install.sh
asks for them where it finds an NVIDIA card); loading them first by their full path, shared,
is enough, with no LD_LIBRARY_PATH. Measured on the RTX 5070 (docs/dev/facts.md).
"""
from __future__ import annotations

import ctypes
import importlib.util
import os
import threading

# The versions the voice clone already ran with on this card; CUDA 12, cuDNN 9.
WHISPER_PACKAGES = ("nvidia-cublas-cu12==12.8.4.1", "nvidia-cudnn-cu12==9.10.2.21")
# The voice also needs these, and onnxruntime-gpu in place of onnxruntime (the same module, so
# one replaces the other). 1.26 is its last release built for CUDA 12; 1.27 on wants CUDA 13.
VOICE_PACKAGES = WHISPER_PACKAGES + ("nvidia-cuda-runtime-cu12==12.8.90", "nvidia-curand-cu12==10.3.9.90",
                                     "nvidia-cufft-cu12==11.3.3.83", "nvidia-cuda-nvrtc-cu12==12.8.93")
ONNXRUNTIME = "onnxruntime-gpu==1.26.0"
WHISPER_PARTS = ("cublas", "cudnn")
VOICE_PARTS = WHISPER_PARTS + ("cuda_runtime", "curand", "cufft", "cuda_nvrtc")

_loaded: dict = {}  # path: the library, kept so it stays loaded
_lock = threading.Lock()


def libraries(parts=WHISPER_PARTS, roots=None) -> list:
    """The .so files of NVIDIA's pip packages `parts` under `roots` (the `nvidia` package folders)."""
    if roots is None:
        spec = importlib.util.find_spec("nvidia")
        roots = list(spec.submodule_search_locations or []) if spec else []
    found = []
    for root in roots:
        for part in parts:
            folder = os.path.join(root, part, "lib")
            if os.path.isdir(folder):
                found += sorted(os.path.join(folder, f) for f in os.listdir(folder) if ".so" in f)
    return found


def load(parts=WHISPER_PARTS, roots=None) -> str:
    """Load NVIDIA's libraries `parts`: "" when done, else what is missing."""
    files = libraries(parts, roots)
    missing = [p for p in parts if not any(f"{os.sep}{p}{os.sep}" in f for f in files)]
    if missing:
        return "NVIDIA's " + ", ".join(missing) + " not installed"
    with _lock:
        left = [f for f in files if f not in _loaded]
        while left:  # one library needs another: load what can be, again, until nothing more can
            failed = []
            for f in left:
                try:
                    _loaded[f] = ctypes.CDLL(f, mode=ctypes.RTLD_GLOBAL)
                except OSError:
                    failed.append(f)
            if len(failed) == len(left):
                return "could not load " + os.path.basename(failed[0])
            left = failed
    return ""
