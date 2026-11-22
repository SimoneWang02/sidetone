"""build_voice.py RECORDINGS_DIR OUT_DIR LANG:TEXT ...

A voice profile from every kept recording, with no training: the speaker fingerprint averaged
over all of them, and as the example the clearest 10 s of speech (pauses cut out) from the
longest ones. Then says each line in it, saved as 1.wav, 2.wav, ... in OUT_DIR."""
import json, os, sys, time
import librosa, numpy as np, torch, torchaudio as ta
from chatterbox.mtl_tts import ChatterboxMultilingualTTS, Conditionals, T3Cond, S3GEN_SR, S3_SR

rec, out, lines = sys.argv[1], sys.argv[2], sys.argv[3:]
items = [json.loads(l) for l in open(os.path.join(rec, "list.jsonl"))]
wavs = {i["file"]: librosa.load(os.path.join(rec, i["file"]), sr=S3_SR)[0] for i in items}

def speech(w):
    """The spoken parts only, each with a short breath of pause kept. The first 0.35 s and the
    last 0.5 s go first: the talk key's click going down, and coming up in the release delay.
    A part under 0.25 s is a click or a knock, not a word."""
    w = w[int(0.35 * S3_SR):len(w) - int(0.5 * S3_SR)]
    pad = int(0.12 * S3_SR)
    return [w[max(0, a - pad):b + pad] for a, b in librosa.effects.split(w, top_db=35) if b - a > 0.25 * S3_SR]


def tidy(wav, sr):
    """Cuts a short burst of noise before the first word or after the last (under 0.3 s, apart
    from the speech), and fades the ends over 20 ms so the cut does not click."""
    w = wav[0].numpy()
    parts = [(a, b) for a, b in librosa.effects.split(w, top_db=35)]
    while len(parts) > 1 and parts[0][1] - parts[0][0] < 0.3 * sr:
        parts.pop(0)
    while len(parts) > 1 and parts[-1][1] - parts[-1][0] < 0.3 * sr:
        parts.pop()
    w = w[max(0, parts[0][0] - int(0.05 * sr)):parts[-1][1] + int(0.1 * sr)].copy()
    fade = int(0.02 * sr)
    w[:fade] *= np.linspace(0, 1, fade)
    w[-fade:] *= np.linspace(1, 0, fade)
    return torch.from_numpy(w).unsqueeze(0)

# The example: speech from the longest recordings until 10 s, loudness evened out.
example, total = [], 0
for i in sorted(items, key=lambda i: -i["seconds"]):
    for part in speech(wavs[i["file"]]):
        part = part / (np.abs(part).max() + 1e-6) * 0.9
        example.append(part)
        total += len(part)
        if total >= 10 * S3_SR:
            break
    if total >= 10 * S3_SR:
        break
example = np.concatenate(example)[:10 * S3_SR]

model = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
ref_24k = librosa.resample(example, orig_sr=S3_SR, target_sr=S3GEN_SR)
s3gen_ref = model.s3gen.embed_ref(ref_24k, S3GEN_SR, device=model.device)
tokens, _ = model.s3gen.tokenizer.forward([example[:model.ENC_COND_LEN]], max_len=model.t3.hp.speech_cond_prompt_len)
fingerprint = model.ve.embeds_from_wavs(list(wavs.values()), sample_rate=S3_SR)  # one per recording
fingerprint = torch.from_numpy(fingerprint).mean(axis=0, keepdim=True).to(model.device)
model.conds = Conditionals(T3Cond(speaker_emb=fingerprint, cond_prompt_speech_tokens=torch.atleast_2d(tokens).to(model.device),
                                  emotion_adv=0.5 * torch.ones(1, 1, 1)).to(device=model.device), s3gen_ref)
os.makedirs(out, exist_ok=True)
ta.save(os.path.join(out, "example.wav"), torch.from_numpy(example).unsqueeze(0), S3_SR)
print(f"profile from {len(items)} recordings ({sum(i['seconds'] for i in items) / 60:.1f} min)", flush=True)
for n, line in enumerate(lines, 1):
    lang, text = line.split(":", 1)
    t = time.monotonic()
    wav = tidy(model.generate(text, language_id=lang), model.sr)
    ta.save(os.path.join(out, f"{n}.wav"), wav, model.sr)
    print(f"{n} {lang}: {wav.shape[-1] / model.sr:.1f}s made in {time.monotonic() - t:.1f}s", flush=True)
