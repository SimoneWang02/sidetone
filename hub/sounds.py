"""Short sounds the hub answers with, made in code: there are no audio files.

They are played by their own `paplay`, beside the voice and not through its queue, so a sound
is heard the moment something happens even while a session is speaking.
"""
from __future__ import annotations

import array
import math
import shutil
import subprocess
import threading

RATE = 24000
# What each sound is: notes as (pitch in Hz, seconds); pitch 0 is a pause. They are told apart
# by their shape: going up = sent, the same note twice = waiting, going down = not sent.
TONES = {
    "sent": [(659.3, 0.07), (987.8, 0.13)],
    "queued": [(659.3, 0.07), (0, 0.06), (659.3, 0.11)],
    "failed": [(440.0, 0.08), (329.6, 0.16)],
    # The mute key: lower and slower than the three above, so they are not taken for them.
    "voice_off": [(392.0, 0.09), (261.6, 0.2)],
    "voice_on": [(261.6, 0.09), (392.0, 0.2)],
}


def tone(notes: list, volume: float) -> bytes:
    """The notes as 16-bit mono sound. Each one starts softly within 4 ms and dies away, so
    there is no click at either end."""
    volume = max(0.0, min(1.0, float(volume)))
    out = array.array("h")
    for pitch, seconds in notes:
        count = int(RATE * seconds)
        for i in range(count):
            t = i / RATE
            rise = min(1.0, t / 0.004)
            fall = math.exp(-3.0 * i / count) * min(1.0, (count - i) / (RATE * 0.008))
            wave = math.sin(2 * math.pi * pitch * t) + 0.25 * math.sin(4 * math.pi * pitch * t)
            out.append(int(32767 * 0.8 * volume * rise * fall * wave) if pitch else 0)
    return out.tobytes()


class Sounds:
    def __init__(self, volume: float = 0.3):
        self.volume = volume
        self._made: dict[str, bytes] = {}

    @staticmethod
    def available() -> bool:
        return bool(shutil.which("paplay"))

    def play(self, name: str) -> bool:
        """Start the sound and return at once. False for a name that is not a sound."""
        if name not in TONES:
            return False
        if name not in self._made:
            self._made[name] = tone(TONES[name], self.volume)
        threading.Thread(target=self._out, args=(self._made[name],), daemon=True).start()
        return True

    def _out(self, pcm: bytes) -> None:
        try:
            subprocess.run(["paplay", "--raw", f"--rate={RATE}", "--format=s16le", "--channels=1",
                            "--latency-msec=30"], input=pcm, timeout=5,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            pass  # no sound is not worth failing over
