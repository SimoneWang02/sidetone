"""say.py REF OUT_DIR LANG:TEXT ... : each line in the voice cloned from REF, saved as 1.wav, 2.wav, ..."""
import sys, time, torchaudio as ta
from chatterbox.mtl_tts import ChatterboxMultilingualTTS

ref, out, lines = sys.argv[1], sys.argv[2], sys.argv[3:]
model = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
model.prepare_conditionals(ref)
for i, line in enumerate(lines, 1):
    lang, text = line.split(":", 1)
    t = time.monotonic()
    wav = model.generate(text, language_id=lang)
    ta.save(f"{out}/{i}.wav", wav, model.sr)
    print(f"{i} {lang}: {wav.shape[-1] / model.sr:.1f}s made in {time.monotonic() - t:.1f}s", flush=True)
