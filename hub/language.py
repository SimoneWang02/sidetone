"""The language of a spoken line whose speak tag has no `lang`.

The reminder asks each session to mark a line that is not in English (lang="it"), and the hub
gives it a voice of that language. A session sometimes answers in Italian without the mark
(seen 2026-11-19), and then the English voice read Italian words. This guesses from the words
themselves, only for lines with no mark, and says "" (English) whenever it is not sure.

Chinese, Japanese and Hindi show in their script. The languages written in Latin letters with a
Kokoro voice (Italian, Spanish, French, Portuguese) are told apart from English by their small
everyday words and accents: a two-sentence line has a dozen of them. Words two languages share
with English ("come", "no", "a", "in") are left out, so an English line that names an Italian
word or two stays English.
"""
from __future__ import annotations

import re

_HAN = re.compile(r"[㐀-䶿一-鿿]")
_KANA = re.compile(r"[぀-ヿ]")
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_WORD = re.compile(r"[^\W\d_]+")  # "c'è" and "don't" are two words each: the apostrophe parts them

EN = set("""the and is are was were be been to of you your it its that this these with for have
has had what which on not can will would should could we they them their there from at or an i my
me now just done next also than then all if but by about want need yes""".split())

WORDS = {
    "it": set("""il lo gli di del della dello delle dei degli che non sono è ho hai abbiamo hanno per
questo questa questi quello quella perché anche ancora già più fatto fatta adesso vuoi posso puoi
devo nel nella sul sulla alla alle allo cosa tutto tutti bene sì ecco poi mi ti ci si va fa era
molto ora prima dopo quando dove sei siamo funziona provato aggiunto messo detto""".split()),
    "es": set("""el los las del que es está están son por para pero muy también ya más hecho ahora
quieres puedo puedes tengo hay cómo qué sí esto este esta eso todo bien y lo una con se mi te
nos fue era donde cuando""".split()),
    "fr": set("""le les des du est sont je tu nous vous et une pas que qui pour dans avec sur ce cette
mais plus fait maintenant veux peux oui très aussi déjà à ça été était où quand ai avez avons""".split()),
    "pt": set("""os das dos da não é são está para por com uma um que mas também já mais feito agora
quer posso pode sim isso isto este esta tudo bem você eu em na nos nas foi era onde quando""".split()),
}
# Letters one language has and the others mostly do not: each word with one is one more vote.
LETTERS = {"it": "èìòù", "es": "ñ¿¡", "fr": "êâîûœë", "pt": "ãõ"}


def guess(text: str, spoken: list | tuple = ()) -> str:
    """The two-letter code of the language `text` is in, or "" for English or not sure.

    `spoken`: the languages the user speaks (`whisper_language`); with one besides English
    named there, only those are guessed among the Latin-letter ones, which keeps Italian
    apart from Spanish. With none named (English only, or "auto"), all four are."""
    text = str(text or "")
    if len(_KANA.findall(text)) >= 2:
        return "ja"
    if len(_HAN.findall(text)) >= 2:
        return "zh"
    if len(_DEVANAGARI.findall(text)) >= 2:
        return "hi"
    words = [w.lower() for w in _WORD.findall(text)]
    if not words:
        return ""
    named = [c for c in spoken if c in WORDS]
    score = {}
    for lang in named or WORDS:
        votes = sum(w in WORDS[lang] for w in words)
        votes += sum(any(ch in LETTERS[lang] for ch in w) for w in words)
        score[lang] = votes
    english = sum(w in EN for w in words)
    ranked = sorted(score.items(), key=lambda kv: -kv[1])
    best, votes = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0
    # Sure enough: two clear signs at least, twice as many as the English ones, and ahead of
    # the next language.
    if votes >= 2 and votes >= 2 * english and votes > runner_up:
        return best
    return ""
