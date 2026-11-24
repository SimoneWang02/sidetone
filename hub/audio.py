"""Sound out and in, 16-bit mono, on whichever system the hub runs.

Linux and WSL have PulseAudio's `paplay` and `parec`, which the hub has always used. A Mac has
neither, so there the sound goes through PortAudio, by the `sounddevice` package (its wheels for
macOS and Windows carry PortAudio itself). PulseAudio stays first where it is: the buffer sizes
that cured the scratches through WSL were measured with it (see tts.KokoroEngine.LATENCY_MS).
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import threading
from typing import Callable


def pulse() -> bool:
    return bool(shutil.which("paplay"))


def _sounddevice():
    """The sounddevice module, or None when it or PortAudio is missing."""
    if not importlib.util.find_spec("sounddevice"):
        return None
    try:
        import sounddevice
        return sounddevice
    except (ImportError, OSError):  # installed, but PortAudio itself is not there (Linux without it)
        return None


def can_play() -> bool:
    return pulse() or _sounddevice() is not None


def can_record() -> bool:
    if shutil.which("parec"):
        return True
    sd = _sounddevice()
    if sd is None:
        return False
    try:
        return any(d.get("max_input_channels", 0) > 0 for d in sd.query_devices())
    except Exception:  # noqa: BLE001  no device list at all
        return False


def _scaled(pcm: bytes, volume: float) -> bytes:
    if volume >= 0.999:
        return pcm
    import array
    samples = array.array("h", pcm[:len(pcm) // 2 * 2])
    for i, x in enumerate(samples):
        samples[i] = int(x * volume)
    return samples.tobytes()


class Player:
    """One stream of sound being played: write() pieces of it, then finish() to let it play
    out, or kill() from another thread to cut it off at once."""

    def __init__(self, rate: int, latency_ms: int, volume: float):
        self.rate, self.volume = rate, max(0.0, min(1.0, volume))
        self._proc: subprocess.Popen | None = None
        self._stream = None
        self._killed = False
        if pulse():
            self._proc = subprocess.Popen(
                ["paplay", "--raw", f"--rate={rate}", "--format=s16le", "--channels=1", f"--latency-msec={latency_ms}",
                 f"--volume={round(65536 * self.volume)}"],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        sd = _sounddevice()
        if sd is None:
            raise OSError("no way to play sound: neither paplay nor sounddevice")
        try:
            self._stream = sd.RawOutputStream(samplerate=rate, channels=1, dtype="int16", latency=latency_ms / 1000)
            self._stream.start()
        except Exception as e:  # noqa: BLE001  PortAudio's own error: no device, busy device
            raise OSError(f"sound could not start: {e}") from e

    def write(self, pcm: bytes) -> None:
        if self._killed:
            raise OSError("cut off")
        if self._proc:
            self._proc.stdin.write(pcm)
            self._proc.stdin.flush()
            return
        try:  # blocks while the buffer is full, as a write to paplay does
            self._stream.write(_scaled(pcm, self.volume))
        except Exception as e:  # noqa: BLE001
            raise OSError(f"sound cut off: {e}") from e

    def finish(self) -> None:
        """Wait until all that was written has been heard."""
        if self._proc:
            self._proc.stdin.close()
            self._proc.wait()
            return
        try:
            if not self._killed:
                self._stream.stop()  # returns once the buffers have played
            self._stream.close()
        except Exception as e:  # noqa: BLE001
            raise OSError(str(e)) from e

    def alive(self) -> bool:
        if self._proc:
            return self._proc.poll() is None
        return not self._killed and self._stream is not None and self._stream.active

    def kill(self) -> None:
        self._killed = True
        if self._proc:
            if self._proc.poll() is None:
                self._proc.kill()
            return
        try:
            self._stream.abort()
        except Exception:  # noqa: BLE001  already closed
            pass


def play(pcm: bytes, rate: int, latency_ms: int, volume: float) -> None:
    """Play a short sound to its end (the hub's signals). Quietly nothing when it cannot."""
    try:
        player = Player(rate, latency_ms, volume)
        player.write(pcm)
        player.finish()
    except (OSError, ValueError):
        pass


class Recording:
    """The microphone, 16-bit mono at `rate`, handed out in pieces of `chunk` bytes as they come."""

    def __init__(self, rate: int, chunk: int, on_chunk: Callable[[bytes], None], source: str = "",
                 latency_ms: int = 50):
        self._proc: subprocess.Popen | None = None
        self._stream = None
        self._reader: threading.Thread | None = None
        if shutil.which("parec"):
            cmd = ["parec", f"--rate={rate}", "--channels=1", "--format=s16le", "--raw", f"--latency-msec={latency_ms}"]
            if source:
                cmd.append(f"--device={source}")
            proc = self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

            def read() -> None:
                while True:
                    piece = proc.stdout.read(chunk)
                    if not piece:
                        return
                    on_chunk(piece)
            self._reader = threading.Thread(target=read, daemon=True)
            self._reader.start()
            return
        sd = _sounddevice()
        if sd is None:
            raise OSError("no way to record: neither parec nor sounddevice")

        def heard(data, frames, time, status) -> None:  # PortAudio's own thread
            on_chunk(bytes(data))
        try:
            self._stream = sd.RawInputStream(samplerate=rate, channels=1, dtype="int16", blocksize=chunk // 2,
                                             device=source or None, callback=heard)
            self._stream.start()
        except Exception as e:  # noqa: BLE001  no microphone, or not allowed to use it
            raise OSError(f"the microphone could not start: {e}") from e

    def stop(self) -> None:
        if self._proc:
            proc, self._proc = self._proc, None
            proc.terminate()
            if self._reader:
                self._reader.join(2)
            try:  # reaped, so a finished parec does not stay in the process list looking like a recording
                proc.wait(2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            if proc.stdout:
                proc.stdout.close()
            return
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:  # noqa: BLE001
                pass
