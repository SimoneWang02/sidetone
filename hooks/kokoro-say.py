"""Read text on stdin, write 24 kHz mono s16le PCM to stdout using Kokoro."""
import os, sys
import numpy as np
from kokoro_onnx import Kokoro

home = os.path.expanduser(os.environ.get("KOKORO_DIR", "~/.local/share/kokoro"))
voice = os.environ.get("KOKORO_VOICE", "af_heart")
speed = float(os.environ.get("KOKORO_SPEED", "1.1"))

text = sys.stdin.read().strip()
if text:
    k = Kokoro(f"{home}/kokoro-v1.0.onnx", f"{home}/voices-v1.0.bin")
    samples, rate = k.create(text, voice=voice, speed=speed, lang="en-us")
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
    sys.stdout.buffer.write(pcm)
