"""The voice on a Mac: python3 tests/mac_voice_check.py KOKORO_DIR

Kokoro loaded as the hub loads it (tts.make_engine), a line made on Apple Silicon's processor
and played through PortAudio (hub/audio.py), then a short recording from the microphone, if the
machine has the devices. Prints the times. For GitHub's Macs, which may have no sound devices.
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hub"))
import audio  # noqa: E402
import tts  # noqa: E402

kokoro_dir = sys.argv[1]
print("  can play:", audio.can_play(), " can record:", audio.can_record(), " paplay:", audio.pulse())
try:
    import sounddevice
    print("  devices:", [d["name"] for d in sounddevice.query_devices()])
except Exception as e:  # noqa: BLE001
    print("  devices: none,", e)
engine = tts.make_engine("auto", kokoro_dir, 1.0, "af_heart")
print("  engine:", type(engine).__name__)
started = time.monotonic()
engine.load()
print(f"  loaded in {time.monotonic() - started:.1f} s on {getattr(engine, 'running', '?')}")
engine.arm()
for line in ("All forty two tests pass.", "The flaky one was a race in the login mock, which I fixed."):
    made = time.monotonic()
    pcm = engine._pcm(line, "af_heart")
    print(f"  made {len(pcm) / 2 / engine.RATE:.1f} s of voice in {time.monotonic() - made:.2f} s: {line}")
said = time.monotonic()
first = engine.speak(["All forty two tests pass."], "af_heart")
print(f"  speak(): first sound after {first} s, done in {time.monotonic() - said:.1f} s (None = nothing could play)")
if audio.can_record():
    got = []
    try:
        rec = audio.Recording(16000, 1600, got.append)
        time.sleep(0.5)
        rec.stop()
        print(f"  recorded {sum(map(len, got)) / 2 / 16000:.2f} s from the microphone")
    except OSError as e:
        print("  recording failed:", e)
