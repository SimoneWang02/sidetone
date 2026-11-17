"""Manual measurement: how long push-to-talk takes to turn speech into text, by choice of languages.

It speaks English and Italian sentences of three lengths with Kokoro, then times the hub's own
`stt.Transcriber` on them for each choice (`claude-speaks languages ...`): English alone, one
other language, two, five, any. Prints a table; with a path as argument also writes the numbers
as JSON. Not part of the test run (it loads two Whisper models and takes a few minutes).

Run: ~/.local/share/kokoro/venv/bin/python -I tests/stt_speed.py [OUT.json] [--runs 5]
"""
import json
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hub"))
import stt  # noqa: E402

KOKORO_DIR = os.environ.get("KOKORO_DIR") or os.path.expanduser("~/.local/share/kokoro")
SPOKEN = {  # language: (Kokoro voice, Kokoro pronunciation, sentences short to long)
    "en": ("af_heart", "en-us", [
        "Run the tests again.",
        "Please rename the settings file and update every place that reads it.",
        "The bar looks right now, but when I move the mouse over it the panel still opens. Can you add a "
        "setting so that it only opens while I hold the keys, and keep the old behaviour as the default?",
    ]),
    "it": ("if_sara", "it", [
        "Rilancia i test.",
        "Per favore rinomina il file delle impostazioni e aggiorna tutti i punti che lo leggono.",
        "Adesso la barra va bene, ma quando ci passo sopra con il mouse il pannello si apre ancora. Puoi "
        "aggiungere un'impostazione per aprirlo solo mentre tengo premuti i tasti, lasciando il "
        "comportamento di prima come predefinito?",
    ]),
}
CHOICES = [  # (what the user chose, the clips' languages it is measured on)
    ("en", ["en"]),
    ("it", ["it"]),
    ("en,it", ["en", "it"]),
    ("en,it,es,fr,de", ["en", "it"]),
    ("auto", ["en", "it"]),
]


def clips() -> list:
    """Each sentence as (language, words, seconds, 16 kHz PCM), the form the microphone gives."""
    import numpy as np
    from kokoro_onnx import Kokoro

    kokoro, made = Kokoro(f"{KOKORO_DIR}/kokoro-v1.0.onnx", f"{KOKORO_DIR}/voices-v1.0.bin"), []
    for language, (voice, lang, sentences) in SPOKEN.items():
        for words in sentences:
            samples, rate = kokoro.create(words, voice=voice, speed=1.0, lang=lang)
            at = np.arange(0, len(samples), rate / stt.RATE)  # 24 kHz to Whisper's 16 kHz
            pcm = (np.interp(at, np.arange(len(samples)), samples) * 32767).astype("<i2").tobytes()
            made.append((language, words, len(samples) / rate, pcm))
    return made


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    runs = int(sys.argv[sys.argv.index("--runs") + 1]) if "--runs" in sys.argv else 5
    args = [a for a in args if not a.isdigit()]
    spoken, rows = clips(), []
    for choice, languages in CHOICES:
        model, setting = stt.setup(choice)
        listener = stt.Transcriber(model, setting)
        started = time.monotonic()
        listener.load()
        loaded = time.monotonic() - started
        listener.transcribe(spoken[0][3])  # the first use is slower; not counted
        for language, words, seconds, pcm in spoken:
            if language not in languages:
                continue
            times, heard, text = [], "", ""
            for _ in range(runs):
                started = time.monotonic()
                text = listener.transcribe(pcm)
                times.append(time.monotonic() - started)
                heard = listener.heard
            rows.append({"choice": choice, "model": model, "load": round(loaded, 2), "spoken": language,
                         "seconds": round(seconds, 1), "median": round(statistics.median(times), 2),
                         "fastest": round(min(times), 2), "slowest": round(max(times), 2),
                         "taken_as": heard, "text": text, "said": words})
            print(f"{choice:16} {model:9} {language}  {seconds:5.1f}s speech  median {rows[-1]['median']:.2f}s "
                  f"({rows[-1]['fastest']:.2f} to {rows[-1]['slowest']:.2f})  as {heard}: {text[:60]}", flush=True)
        listener.unload()
    if args:
        with open(args[0], "w") as f:
            json.dump({"runs": runs, "cpus": os.cpu_count(), "rows": rows}, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
