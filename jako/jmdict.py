"""JMdict (jmdict-simplified JSON) helpers: headwords, deinflection rules, ranking, prompt text."""
import hashlib
import json
from collections import Counter

from .paths import JMDICT

SEARCH_ONLY = {"sK", "sk"}
# Irregular / outdated / rare forms: still searchable, ranked below the regular form.
DISPREFERRED = {"iK", "ik", "io", "oK", "ok", "rK", "rk", "sK", "sk", "ateji"}


def load():
    with open(JMDICT, encoding="utf-8") as f:
        return json.load(f)


def rule_of(pos):
    """Map a JMdict part-of-speech code to a Yomitan deinflection rule (or None)."""
    if pos in ("v1", "v1-s"):
        return "v1"
    if pos.startswith("v5"):
        return "v5"
    if pos in ("vs", "vs-i", "vs-s"):
        return "vs"
    if pos in ("vk", "vz"):
        return pos
    if pos in ("adj-i", "adj-ix"):
        return "adj-i"
    return None


def _applies(restriction, text):
    return "*" in restriction or text in restriction


def headwords(entry):
    """Yield (kanji, kana) pairs; kanji is None for kana-only headwords."""
    if entry["kanji"]:
        for k in entry["kanji"]:
            for r in entry["kana"]:
                if r["appliesToKanji"] and _applies(r["appliesToKanji"], k["text"]) and not SEARCH_ONLY & set(r["tags"]):
                    yield k, r
        # kana flagged as "no kanji" (re_nokanji)
        for r in entry["kana"]:
            if not r["appliesToKanji"]:
                yield None, r
    else:
        for r in entry["kana"]:
            yield None, r


def sense_indices(entry, kanji, kana):
    """Indices of senses that apply to this headword pair."""
    out = []
    for i, s in enumerate(entry["sense"]):
        if kanji is not None and not _applies(s["appliesToKanji"], kanji["text"]):
            continue
        if not _applies(s["appliesToKana"], kana["text"]):
            continue
        out.append(i)
    return out


def is_common(entry):
    return any(f["common"] for f in entry["kanji"] + entry["kana"])


def display_forms(entry):
    kanji = [k["text"] for k in entry["kanji"] if not SEARCH_ONLY & set(k["tags"])]
    kana = [r["text"] for r in entry["kana"] if not SEARCH_ONLY & set(r["tags"])]
    return kanji, kana


def source_hash(entry):
    """Fingerprint of everything the translation depends on; a change means re-translate."""
    payload = [
        [s["partOfSpeech"], s["misc"], s["field"], [g["text"] for g in s["gloss"]], s["info"]]
        for s in entry["sense"]
    ]
    return hashlib.sha1(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()[:12]


def rank(entries):
    """Order entries by usefulness: common words first, then by corpus frequency (wordfreq)."""
    from wordfreq import get_frequency_dict

    freq = get_frequency_dict("ja")

    def forms(e):
        kanji, kana = display_forms(e)
        usually_kana = any("uk" in s["misc"] for s in e["sense"][:1])
        return kanji + (kana if usually_kana or not kanji else [])

    # Homographs (人: ひと/にん/じん, たい: 鯛/助動詞) share one corpus count, so split it between them.
    sharing = Counter(f for e in entries for f in set(forms(e)))

    def score(e):
        best = max((freq.get(f, 0.0) / sharing[f] for f in forms(e)), default=0.0)
        return (not is_common(e), -best, int(e["id"]))

    return sorted(entries, key=score)


def _sense_label(s):
    tags = ",".join(s["partOfSpeech"])
    extra = s["misc"] + s["field"] + s["dialect"]
    if extra:
        tags += "; " + ",".join(extra)
    return tags


def entry_prompt(entry):
    kanji, kana = display_forms(entry)
    head = f"#{entry['id']} " + (f"{', '.join(kanji[:4])}【{', '.join(kana[:3])}】" if kanji else ", ".join(kana[:3]))
    lines = [head]
    for n, s in enumerate(entry["sense"], 1):
        line = f"{n}. ({_sense_label(s)}) " + "; ".join(g["text"] for g in s["gloss"])
        if s["info"]:
            line += f" [note: {' / '.join(s['info'])}]"
        restricted = [t for t in s["appliesToKanji"] + s["appliesToKana"] if t != "*"]
        if restricted:
            line += f" [only: {', '.join(restricted)}]"
        lines.append(line)
        for ex in s["examples"][:1]:
            jp = next((x["text"] for x in ex["sentences"] if x["lang"] == "jpn"), None)
            if jp:
                lines.append(f"   例: {jp}")
    return "\n".join(lines)
