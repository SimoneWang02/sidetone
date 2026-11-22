# Your own voice (trial)

Not part of Sidetone yet: scripts tried on 2026-11-22 to make a voice that sounds like the
author, from the recordings `keep_recordings` saves. See TODO.md, step 3.

Chatterbox Multilingual in its own venv, kept apart from the Kokoro one:

    uv venv --python 3.11 ~/.local/share/voice-clone/venv
    printf 'torch==2.8.0\ntorchaudio==2.8.0\n' > overrides.txt   # 2.6, its pin, has no RTX 50 support
    uv pip install --python ~/.local/share/voice-clone/venv/bin/python --override overrides.txt \
        --extra-index-url https://download.pytorch.org/whl/cu128 --index-strategy unsafe-best-match \
        chatterbox-tts "setuptools<81"

- `build_voice.py RECORDINGS OUT LANG:TEXT ...`: a voice from every recording (no training) and
  the lines in it.
- `say.py REF.wav OUT LANG:TEXT ...`: the same from a single recording.
