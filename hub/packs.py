"""Languages as packs to install, so each person chooses how much storage the voices take.

Agreed with the author on 2026-11-23, from a second machine without Chinese ("for chinese i want
to install it from settings no?"): a language is on or off, and on means installed. English is
Kokoro's own model (install.sh fetches it); Italian's two Kokoro voices are in that same model,
so Italian costs nothing; Chinese is Kokoro's Chinese model v1.1-zh and its pronunciation
package. Only the voices someone ticks are fetched (the author: "i dont need all 100 chinese
voices"): Hugging Face has each Chinese voice on its own, about 0.5 MB, so a voice ticked later
is half a megabyte, and the 325 MB model is what every Chinese voice shares. A Piper voice is a
model of its own (Paola 63 MB, the Piper program 26 MB once).

Everything is fetched from a fixed version and checked against its size, and its SHA-256 where
it is known, before it is put in place; a download cut off leaves only a ".part" file.

Command line (in the hub's environment, used by `sidetone languages` and install.sh):
    packs.py languages CONFIG CODES   turn on these languages, fetching what they need first
    packs.py status                   what each language takes and whether it is installed
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

KOKORO_DIR = os.path.expanduser("~/.local/share/kokoro")
PIPER_DIR = os.path.expanduser("~/.local/share/piper")

# Kokoro's Chinese model: the ONNX file from kokoro-onnx's release, its vocabulary and the voices
# from hexgrad's own repository, pinned to one commit. kokoro-onnx's voices-v1.1-zh.bin holds the
# same arrays as these .pt files (zf_049 compared, equal to the last bit, 2026-11-23).
ZH_MODEL = ("https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.1-zh.onnx",
            325506167, "859f9ded9f53be16c24857cdab3254a45da53c3afd5ba6ef134c7de3f822e326")
ZH_REPO = "https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh/resolve/01e7505bd6a7a2ac4975463114c3a7650a9f7218/"
ZH_CONFIG = (ZH_REPO + "config.json", 3228, "bc333efa5ce4ceff433c8c8e5d027a1eca0166001e4e4a62bea2d26ff7a46890")
ZH_VOICE_BYTES = 523500  # each voice's .pt, about (523331 to 523425)
ZH_PACKAGE = "misaki-fork[zh]==0.9.6"  # Chinese characters to phonemes; the version on the author's main machine
ZH_PACKAGE_BYTES = 100_000_000  # installed, measured 2026-11-23 (jieba's and pypinyin's word lists most of it)
# The files beside Kokoro's own, as tts.KokoroEngine.ZH_FILES names them.
ZH_FILES = ("kokoro-v1.1-zh.onnx", "voices-v1.1-zh.bin", "config-v1.1-zh.json")

PIPER_PROGRAM = ("https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz",
                 26460462, "a50cb45f355b7af1f6d758c1b360717877ba0a398cc8cbe6d2a7a3a26e225992")
PIPER_VOICES = "https://huggingface.co/rhasspy/piper-voices/resolve/e5349433ed883a32f893a434dc43a6c66b95ef7c/"
# Piper's voices that can be fetched: the model and its settings (sample rate), by the voice's name.
PIPER = {
    "piper:it_IT-paola-medium": (
        (PIPER_VOICES + "it/it_IT/paola/medium/it_IT-paola-medium.onnx", 63221984,
         "f9b8658aa8c01f8280aa88488f6e7643a639b6225a81514c40440a01f6364a20"),
        (PIPER_VOICES + "it/it_IT/paola/medium/it_IT-paola-medium.onnx.json", 6114,
         "10e46e8534dd2d4051f1534ba6542f189f854454acea44a6d45ff464a83260fa")),
}

# The multilingual speech model push-to-talk needs once any language but English is on (the
# English-only one is a separate download of the same size). Whisper "small": about 480 MB.
WHISPER_BYTES = {"tiny": 75_000_000, "base": 145_000_000, "small": 484_000_000, "medium": 1_530_000_000}


class Failed(Exception):
    """A download or an install that did not work; the message says what to do."""


def _python() -> str:
    return sys.executable


def has_zh_package() -> bool:
    """Whether misaki, which turns Chinese characters into phonemes, is in this environment."""
    return importlib.util.find_spec("misaki") is not None


# ---- what is there ----

def zh_installed(kokoro_dir: str = KOKORO_DIR) -> list:
    """The Chinese voices installed (zf_049, ...), none when the model or its package is missing."""
    if not all(os.path.isfile(os.path.join(kokoro_dir, f)) for f in (ZH_FILES[0], ZH_FILES[2])):
        return []
    if not has_zh_package():
        return []
    return sorted(_zh_voices(kokoro_dir))


def _zh_voices(kokoro_dir: str) -> dict:
    import numpy as np

    try:
        with np.load(os.path.join(kokoro_dir, ZH_FILES[1])) as saved:
            return {name: saved[name] for name in saved.files}
    except (OSError, ValueError):
        return {}


def piper_installed(voice: str, piper_dir: str = PIPER_DIR) -> bool:
    name = voice.split(":", 1)[1]
    return (os.access(os.path.join(piper_dir, "piper", "piper"), os.X_OK)
            and all(os.path.isfile(os.path.join(piper_dir, "voices", name + end)) for end in (".onnx", ".onnx.json")))


def installed(lang: str, kokoro_dir: str = KOKORO_DIR) -> bool:
    """Whether a language can be spoken here. Chinese needs its pack; every other language Kokoro
    speaks is in Kokoro's own model."""
    return bool(zh_installed(kokoro_dir)) if lang == "zh" else True


def needs(lang: str, voices: list = (), kokoro_dir: str = KOKORO_DIR, piper_dir: str = PIPER_DIR) -> int:
    """About how many bytes turning `lang` on with `voices` would add (0 when nothing is missing).
    Chinese voices are named as tts names them ("zh:zf_049"), Piper's "piper:it_IT-paola-medium"."""
    total = 0
    if lang == "zh":
        if not os.path.isfile(os.path.join(kokoro_dir, ZH_FILES[0])):
            total += ZH_MODEL[1]
        if not has_zh_package():
            total += ZH_PACKAGE_BYTES
        have = _zh_voices(kokoro_dir)
        total += ZH_VOICE_BYTES * sum(1 for v in voices if v.startswith("zh:") and v[3:] not in have)
    for v in voices:
        if v in PIPER and not piper_installed(v, piper_dir):
            if not os.access(os.path.join(piper_dir, "piper", "piper"), os.X_OK):
                total += PIPER_PROGRAM[1]
            total += sum(f[1] for f in PIPER[v])
    return total


def removable(lang: str, kokoro_dir: str = KOKORO_DIR) -> int:
    """About how many bytes removing a language's pack frees."""
    if lang != "zh":
        return 0
    return sum(os.path.getsize(os.path.join(kokoro_dir, f)) for f in ZH_FILES
               if os.path.isfile(os.path.join(kokoro_dir, f)))


def megabytes(n: int) -> str:
    return f"{n / 1e9:.1f} GB" if n >= 1e9 else f"{n / 1e6:.1f} MB" if n < 950_000 else f"{round(n / 1e6)} MB"


def voice_size(voice: str, piper_dir: str = PIPER_DIR) -> int:
    """What fetching one more voice takes, its language's pack being installed: half a megabyte
    for a Chinese voice, a Piper model (and the Piper program the first time)."""
    if voice.startswith("zh:"):
        return ZH_VOICE_BYTES
    if voice in PIPER:
        program = 0 if os.access(os.path.join(piper_dir, "piper", "piper"), os.X_OK) else PIPER_PROGRAM[1]
        return program + sum(f[1] for f in PIPER[voice])
    return 0


# ---- fetching ----

def fetch(source: tuple, dest: str, progress=None) -> None:
    """Download `source` (url, size, sha256 or None) to `dest`, checked before it is put there.
    `progress(done, total)` is called as it goes."""
    url, size, sha = source
    part = dest + ".part"
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    digest, done = hashlib.sha256(), 0
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "sidetone"})
        with urllib.request.urlopen(request, timeout=60) as reply, open(part, "wb") as out:
            while True:
                chunk = reply.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, size)
    except OSError as e:
        _unlink(part)
        raise Failed(f"could not download {os.path.basename(dest)}: {e}") from None
    if (size and done != size) or (sha and digest.hexdigest() != sha):
        _unlink(part)
        raise Failed(f"{os.path.basename(dest)} did not arrive whole (got {done} bytes); try again")
    os.replace(part, dest)


def _unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def voice_from_pt(data: bytes):
    """The style array in one of hexgrad's .pt voice files, read without PyTorch: the file is a
    zip whose `data/0` is the tensor's 510 x 256 floats, little-endian. Nothing in it is run (its
    pickle is not loaded). Raises Failed for anything else."""
    import io

    import numpy as np

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            raw = z.read(next(n for n in names if n.endswith("/data/0")))
            order = z.read(next(n for n in names if n.endswith("/byteorder"))) if any(n.endswith("/byteorder") for n in names) else b"little"
    except (zipfile.BadZipFile, StopIteration, KeyError):
        raise Failed("not a Kokoro voice file") from None
    if order.strip() != b"little" or len(raw) != 510 * 256 * 4:
        raise Failed("not a Kokoro voice file")
    return np.frombuffer(raw, dtype="<f4").reshape(510, 1, 256).astype(np.float32)


def add_zh_voices(names: list, kokoro_dir: str = KOKORO_DIR, progress=None) -> list:
    """Fetch Chinese voices (zf_049, without "zh:") into the Chinese model's voice file, keeping
    those already there. Returns the names added."""
    import numpy as np

    have = _zh_voices(kokoro_dir)
    wanted = [n for n in dict.fromkeys(names) if n not in have]
    with tempfile.TemporaryDirectory(dir=kokoro_dir if os.path.isdir(kokoro_dir) else None) as tmp:
        for i, name in enumerate(wanted):
            if not (name[:2] in ("zf", "zm", "af", "bf") and name[2] == "_" and name[3:].replace("_", "").isalnum()):
                raise Failed(f"no Chinese voice {name}")
            path = os.path.join(tmp, name + ".pt")
            fetch((ZH_REPO + f"voices/{name}.pt", 0, None), path,
                  progress and (lambda d, t, i=i: progress(i * ZH_VOICE_BYTES + d, len(wanted) * ZH_VOICE_BYTES)))
            with open(path, "rb") as f:
                have[name] = voice_from_pt(f.read())
        if wanted:
            dest = os.path.join(kokoro_dir, ZH_FILES[1])
            with open(dest + ".part", "wb") as out:
                np.savez(out, **have)
            os.replace(dest + ".part", dest)
    return wanted


def install_package(spec: str) -> None:
    uv = shutil.which("uv") or os.path.expanduser("~/.local/bin/uv")
    if not os.access(uv, os.X_OK):
        raise Failed("uv is missing (https://docs.astral.sh/uv/), so the Chinese package cannot be installed")
    done = subprocess.run([uv, "pip", "install", "--quiet", "--python", _python(), spec],
                          capture_output=True, text=True)
    if done.returncode != 0:
        raise Failed(f"could not install {spec}: {(done.stderr or done.stdout).strip()[-300:]}")
    importlib.invalidate_caches()


def install_zh(voices: list, kokoro_dir: str = KOKORO_DIR, progress=None, step=None) -> None:
    """Kokoro's Chinese model, its package and `voices` (names without "zh:"). `step(what)` says
    what is being done, `progress(done, total)` how far, in bytes, over the whole pack."""
    total = needs("zh", ["zh:" + v for v in voices], kokoro_dir)
    sofar = [0]

    def part(size):
        start = sofar[0]
        sofar[0] += size
        return progress and (lambda d, t: progress(start + min(d, size), total))

    if not os.path.isfile(os.path.join(kokoro_dir, ZH_FILES[0])):
        step and step("Chinese model")
        fetch(ZH_MODEL, os.path.join(kokoro_dir, ZH_FILES[0]), part(ZH_MODEL[1]))
    if not os.path.isfile(os.path.join(kokoro_dir, ZH_FILES[2])):
        fetch(ZH_CONFIG, os.path.join(kokoro_dir, ZH_FILES[2]))
    if not has_zh_package():
        step and step("Chinese pronunciation")
        install_package(ZH_PACKAGE)
        part(ZH_PACKAGE_BYTES)
        progress and progress(sofar[0], total)
    step and step("Chinese voices")
    have = _zh_voices(kokoro_dir)
    add_zh_voices(voices, kokoro_dir, part(ZH_VOICE_BYTES * sum(1 for v in voices if v not in have)))


def remove_zh(kokoro_dir: str = KOKORO_DIR) -> int:
    """Take the Chinese model and its voices away; the package stays (it is in the hub's own
    environment, and small beside the model). Returns the bytes freed."""
    freed = removable("zh", kokoro_dir)
    for f in ZH_FILES:
        _unlink(os.path.join(kokoro_dir, f))
    return freed


def install_piper(voice: str, piper_dir: str = PIPER_DIR, progress=None) -> None:
    """A Piper voice, with the Piper program the first time."""
    if voice not in PIPER:
        raise Failed(f"no Piper voice {voice} to fetch")
    sources = list(PIPER[voice])
    total = sum(s[1] for s in sources)
    program = os.path.join(piper_dir, "piper", "piper")
    if not os.access(program, os.X_OK):
        total += PIPER_PROGRAM[1]
        with tempfile.TemporaryDirectory() as tmp:
            archive = os.path.join(tmp, "piper.tar.gz")
            fetch(PIPER_PROGRAM, archive, progress and (lambda d, t: progress(d, total)))
            with tarfile.open(archive) as tar:
                tar.extractall(piper_dir, filter="data")  # only files under piper/, no links out
        done = PIPER_PROGRAM[1]
    else:
        done = 0
    for source in sources:
        name = source[0].rsplit("/", 1)[1]
        fetch(source, os.path.join(piper_dir, "voices", name),
              progress and (lambda d, t, start=done: progress(start + d, total)))
        done += source[1]


# ---- turning languages on ----

def turn_on(config_path: str, languages: str, fetch_packs: bool = True, say=print) -> tuple:
    """`sidetone languages en,zh`: fetch what the languages need (the default voices of Chinese),
    then save the choice. A language whose pack did not come is not turned on."""
    import stt
    import tts

    model, language = stt.setup(languages)  # raises ValueError for a wrong code, before anything is fetched
    wanted = stt.codes(languages)
    if fetch_packs and "zh" in wanted and not installed("zh"):
        voices = [v[3:] for v in tts.PREFERRED_VOICE["zh"]]
        say(f"Installing Chinese ({megabytes(needs('zh', tts.PREFERRED_VOICE['zh']))})")
        try:
            install_zh(voices, progress=_bar(say), step=lambda what: say(f"  {what}"))
        except Failed as e:
            raise Failed(f"Chinese was not turned on: {e}") from None
        say("")
    return stt.save_languages(config_path, languages)


def _bar(say):
    """A progress line for a terminal: rewritten in place, one line in a log."""
    last = [-1]

    def show(done, total):
        percent = int(done * 100 / total) if total else 100
        if percent != last[0]:
            last[0] = percent
            if sys.stderr.isatty():
                sys.stderr.write(f"\r  {percent:3d} %  {megabytes(done)} of {megabytes(total)}")
                sys.stderr.flush()
            elif percent % 25 == 0:
                say(f"  {percent} %")
    return show


def status() -> list:
    import tts

    lines = []
    for lang, name in (("en", "English"), ("it", "Italian"), ("zh", "Chinese")):
        if lang == "zh":
            have = zh_installed()
            lines.append(f"{name}: " + (f"installed, {len(have)} voices, {megabytes(removable('zh'))}" if have else
                                        f"not installed, {megabytes(needs('zh', tts.PREFERRED_VOICE['zh']))} with its four voices"))
        else:
            lines.append(f"{name}: in Kokoro's own model")
    return lines


if __name__ == "__main__":
    import stt

    args = sys.argv[1:]
    try:
        if args[:1] == ["languages"] and len(args) >= 3:
            fetch_packs = "--no-download" not in args
            codes = " ".join(a for a in args[2:] if a != "--no-download")
            print(stt.describe(*turn_on(args[1], codes, fetch_packs)))
        elif args == ["status"]:
            print("\n".join(status()))
        else:
            sys.exit("usage: packs.py languages CONFIG CODES [--no-download]  |  packs.py status")
    except (Failed, ValueError) as e:
        sys.exit(str(e))
    except KeyboardInterrupt:
        sys.exit("\nstopped; nothing was turned on")
