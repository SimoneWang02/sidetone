"""Record the samples the settings window plays for voices not downloaded yet (hub/samples/).

    ~/.local/share/kokoro/venv/bin/python -I tests/record_samples.py [WORK_DIR]

Each voice the window can list before it is downloaded says the window's sample sentence
(settings.SAMPLES), at the default speed, and is kept as a small Ogg file: the Chinese voices it
lists (the four Install brings and the clearest after them) and Piper's Paola. The Chinese model
must be installed here (Install in the window, or `sidetone languages en,zh`); the voices that
are missing, and Paola with the Piper program, are fetched into WORK_DIR, not installed.
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hub"))
import numpy as np  # noqa: E402

import base  # noqa: E402
import packs  # noqa: E402
import settings  # noqa: E402
import sndfile  # noqa: E402
import tts  # noqa: E402

work = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="cs-samples-")
kokoro, piper = os.path.join(work, "kokoro"), os.path.join(work, "piper")
os.makedirs(kokoro, exist_ok=True)
if not packs.zh_installed():
    sys.exit("Install Chinese first (the settings window, or: sidetone languages en,zh)")
for name in ("kokoro-v1.0.onnx", "voices-v1.0.bin", packs.ZH_FILES[0], packs.ZH_FILES[2]):
    link = os.path.join(kokoro, name)
    if not os.path.exists(link):
        os.symlink(os.path.join(packs.KOKORO_DIR, name), link)

chinese = list(dict.fromkeys(tts.PREFERRED_VOICE["zh"] + settings.CHINESE_CLARITY[:settings.MOST_VOICES]))
italian = [v for v in packs.PIPER if settings.voice_language(v) == "it"]
print(f"fetching {len(chinese)} Chinese voices and {', '.join(italian)} into {work}")
packs.add_zh_voices([v[3:] for v in chinese], kokoro)
for v in italian:
    if not packs.piper_installed(v, piper):
        packs.install_piper(v, piper)

engine = tts.KokoroEngine(kokoro, base.Config(run="", state="").speed, "af_heart", piper_dir=piper)
engine.load()
os.makedirs(tts.SAMPLES_DIR, exist_ok=True)
for voice in chinese + italian:
    pcm = np.frombuffer(engine._pcm(settings.SAMPLES[settings.voice_language(voice)], voice), dtype="<i2")
    path = tts.sample_path(voice)
    sndfile.write_ogg(path, pcm, engine.RATE)
    print(f"  {os.path.basename(path)}: {len(pcm) / engine.RATE:.1f} s, {os.path.getsize(path) / 1000:.0f} KB")
