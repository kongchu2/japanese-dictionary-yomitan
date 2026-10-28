"""Translate JMdict senses, JMdict tags and kanji 훈음 into Korean with an LLM."""
import json
import re
import sys
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import jmdict
from .llm import ClaudeCLI, RateLimited
from .paths import KANJI_STORE, KANJIDIC, TAGS_FILE, TERMS_STORE
from .store import Store

JAPANESE_SCRIPT = re.compile(r"[぀-ヿ㐀-䶿一-鿿]")
HUNUM = re.compile(r"^[가-힣](?:[가-힣 ,·()]*[가-힣)])? [가-힣]$")  # "날 생", "배울 학"

TERMS_SYSTEM = """You are a professional Japanese–Korean lexicographer writing the Korean side of a Japanese→Korean learner's dictionary built on JMdict.

Each entry has a JMdict id, headwords【readings】, and numbered senses. Each sense shows JMdict part-of-speech/usage tags in parentheses, English glosses, sometimes a note, a headword restriction, or a Japanese example sentence (例).

For every sense, write the Korean equivalents a Korean speaker would expect in a bilingual dictionary.

Rules:
1. Translate the meaning of the Japanese word. The English glosses only tell you which sense is meant; do not translate the English mechanically.
2. Return exactly as many senses as given, in the same order. Never merge, split, skip or reorder senses.
3. Give 1–4 short glosses per sense, most natural first. Prefer real equivalent words. Use a short explanatory phrase only when Korean has no equivalent (こたつ → "고타쓰", "(일본식) 난방 탁자").
4. Do not turn Sino-Japanese words into Sino-Korean readings unless that Korean word is really used with this meaning: 勉強 → 공부 (not 면강), 大丈夫 → 괜찮다 (not 대장부), 手紙 → 편지, 階段 → 계단 (fine, same word).
5. Match the part of speech. Verbs and i-adjectives in dictionary form ending in -다 (食べる → 먹다, 高い → 높다, 비싸다). na-adjectives as -하다 or -한 (静か → 조용하다). Nouns as nouns; suru-nouns as nouns (勉強 → 공부). Adverbs as adverbs. Particles, suffixes, prefixes, counters and auxiliaries: the Korean equivalent pattern with ~ (に → ~에게, ~에; 匹 → ~마리). Never prefix glosses with part-of-speech labels such as (조사), (접미사), (감탄사): the dictionary already shows the part of speech.
6. Keep register: honorific/humble (hon/hum) → Korean honorific/humble forms (召し上がる → 드시다, 申す → 말씀드리다); slang/vulgar → equally informal Korean; archaic → prefix "(고어) ".
7. Onomatopoeia and mimetic words → Korean 의성어·의태어 (ドキドキ → 두근두근, にこにこ → 싱글벙글).
8. Katakana loanwords → standard Korean loanword spelling per 국립국어원 외래어 표기법 (コンピューター → 컴퓨터).
9. Culture-specific or proper-noun-like terms: Hangul transliteration plus a short explanation in parentheses.
10. Technical senses (math, biology, law, Buddhism, …): use the established Korean technical term (系 "corollary" → 따름정리), not a bare one-syllable Sino-Korean reading.
11. Glosses must contain no English, no romanization, no kana and no kanji. Write only Korean (Hangul, with punctuation and ~ allowed).
12. conf: "low" only when you are unsure of the core meaning of some sense (obscure, rare or ambiguous word). Many senses, nuance or register differences alone are not reasons for "low"; otherwise "high"."""

TERMS_SCHEMA = {
    "type": "object",
    "properties": {
        "entries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "senses": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
                    "conf": {"type": "string", "enum": ["high", "low"]},
                },
                "required": ["id", "senses", "conf"],
            },
        }
    },
    "required": ["entries"],
}

TAGS_SYSTEM = """You translate JMdict tag descriptions into Korean for a Japanese→Korean dictionary.
For each tag give:
- short: a compact Korean label as seen in Korean dictionaries, at most 8 characters, no spaces (v1 → 1단동사, v5k → 5단동사, vt → 타동사, vi → 자동사, n → 명사, adj-na → な형용사, adj-i → い형용사, vs → する동사, uk → 주로가나, sl → 속어, hon → 존경어, hum → 겸양어, arch → 고어, iK → 불규칙표기).
- long: a full Korean description of the tag."""

TAGS_SCHEMA = {
    "type": "object",
    "properties": {
        "tags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"tag": {"type": "string"}, "short": {"type": "string"}, "long": {"type": "string"}},
                "required": ["tag", "short", "long"],
            },
        }
    },
    "required": ["tags"],
}

KANJI_SYSTEM = """You write the Korean 훈음 (meaning + Sino-Korean reading) of kanji, exactly as Korean hanja dictionaries do.
Input lines give the kanji (Japanese form), its Korean reading(s) from KANJIDIC if known, Japanese readings and English meanings.
Rules:
- Use the traditional 훈음 of the character, written as "훈 음" (学 → 배울 학, 国 → 나라 국, 円 → 둥글 원).
- Japanese simplified forms (shinjitai) take the 훈음 of their traditional counterpart (図 → 그림 도, 楽 → 즐길 락).
- A character with several readings gets one item per reading, most common first (楽 → "즐길 락", "노래 악", "좋아할 요").
- Write the reading in its dictionary (non-initial-sound-rule) form: 즐길 락, not 즐길 낙.
- Japanese-made characters (kokuji) with no traditional Korean reading: use the given Korean reading if any, otherwise return an empty list.
- Output Hangul only."""

KANJI_SCHEMA = {
    "type": "object",
    "properties": {
        "kanji": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"c": {"type": "string"}, "hunum": {"type": "array", "items": {"type": "string"}}},
                "required": ["c", "hunum"],
            },
        }
    },
    "required": ["kanji"],
}


def _chunk(items, max_items, weight=lambda x: 1, max_weight=None):
    batch, w = [], 0
    for it in items:
        iw = weight(it)
        if batch and (len(batch) >= max_items or (max_weight and w + iw > max_weight)):
            yield batch
            batch, w = [], 0
        batch.append(it)
        w += iw
    if batch:
        yield batch


def _run(batches, worker, workers):
    """Run worker(batch) -> (ok_count, failed_items) in parallel; stop cleanly on rate limits."""
    stop = threading.Event()
    failed, done, total, t0 = [], 0, len(batches), time.time()

    def guarded(b):
        if stop.is_set():
            return 0, []
        try:
            return worker(b)
        except RateLimited as e:
            stop.set()
            print(f"\n!! rate/usage limit reached, stopping: {e}", file=sys.stderr)
            return 0, []
        except Exception as e:  # keep going; the batch stays untranslated and is retried next run
            print(f"\n!! batch failed: {e}", file=sys.stderr)
            return 0, []

    ok = 0
    with ThreadPoolExecutor(workers) as pool:
        for fut in as_completed([pool.submit(guarded, b) for b in batches]):
            n, f = fut.result()
            ok += n
            failed += f
            done += 1
            print(f"[{done}/{total}] ok={ok} failed={len(failed)} {time.time() - t0:.0f}s", flush=True)
    return ok, failed, stop.is_set()


def _valid_senses(senses, expected):
    return (
        len(senses) == expected
        and all(s and all(g.strip() and not JAPANESE_SCRIPT.search(g) for g in s) for s in senses)
    )


def translate_terms(args):
    data = jmdict.load()
    store = Store(Path(args.store) if args.store else TERMS_STORE)
    llm = ClaudeCLI(args.model)

    entries = jmdict.rank(data["words"])
    if args.common_only:
        entries = [e for e in entries if jmdict.is_common(e)]
    todo = [e for e in entries if (store.get(e["id"]) or {}).get("h") != jmdict.source_hash(e)]
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(todo)} entries to translate with {args.model}")

    def worker(batch):
        by_id = {e["id"]: e for e in batch}
        prompt = "\n\n".join(jmdict.entry_prompt(e) for e in batch)
        out = llm.call(TERMS_SYSTEM, prompt, TERMS_SCHEMA)
        recs = []
        for item in out.get("entries", []):
            e = by_id.pop(item.get("id"), None)
            if e is None:
                continue
            senses = [[g.strip() for g in s if g.strip()] for s in item["senses"]]
            if not _valid_senses(senses, len(e["sense"])):
                by_id[e["id"]] = e
                continue
            recs.append({"id": e["id"], "h": jmdict.source_hash(e), "s": senses, "c": item["conf"], "m": args.model})
        store.add_many(recs)
        return len(recs), list(by_id.values())

    batches = list(_chunk(todo, args.batch, weight=lambda e: len(e["sense"]), max_weight=args.batch * 3))
    ok, failed, stopped = _run(batches, worker, args.workers)
    if failed and not stopped:
        print(f"retrying {len(failed)} entries in small batches")
        ok2, failed, stopped = _run(list(_chunk(failed, 3)), worker, args.workers)
        ok += ok2
    store.compact(sort_key=lambda r: int(r["id"]))
    print(f"translated {ok}, still failing {len(failed)}: {' '.join(e['id'] for e in failed[:50])}")
    if stopped:
        sys.exit(75)  # EX_TEMPFAIL: usage limit, run again after it resets


def translate_tags(args):
    data = jmdict.load()
    tags = json.loads(TAGS_FILE.read_text()) if TAGS_FILE.exists() else {}
    todo = {k: v for k, v in data["tags"].items() if k not in tags}
    if not todo:
        print("tags up to date")
        return
    llm = ClaudeCLI(args.model)
    for batch in _chunk(sorted(todo.items()), 80):
        prompt = "\n".join(f"{k}: {v}" for k, v in batch)
        for t in llm.call(TAGS_SYSTEM, prompt, TAGS_SCHEMA)["tags"]:
            if t["tag"] in todo:
                tags[t["tag"]] = {"short": t["short"].replace(" ", ""), "long": t["long"]}
    TAGS_FILE.write_text(json.dumps(dict(sorted(tags.items())), ensure_ascii=False, indent=1) + "\n")
    print(f"{len(tags)} tags translated, missing: {sorted(set(data['tags']) - set(tags))}")


def kanji_candidates(chars):
    """Kanji worth a 훈음: jōyō/jinmeiyō (graded) or newspaper-frequency ranked."""
    out = [c for c in chars if c["misc"].get("grade") or c["misc"].get("frequency")]
    return sorted(out, key=lambda c: (c["misc"].get("frequency") or 9999, c["misc"].get("grade") or 99))


def readings(c, kind):
    rm = c["readingMeaning"]
    return [r["value"] for g in (rm["groups"] if rm else []) for r in g["readings"] if r["type"] == kind]


def meanings(c, lang="en"):
    rm = c["readingMeaning"]
    return [m["value"] for g in (rm["groups"] if rm else []) for m in g["meanings"] if m["lang"] == lang]


def translate_kanji(args):
    chars = json.loads(KANJIDIC.read_text())["characters"]
    store = Store(KANJI_STORE, key="c")
    llm = ClaudeCLI(args.model)
    todo = [c for c in kanji_candidates(chars) if store.get(c["literal"]) is None]
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(todo)} kanji to translate")

    def worker(batch):
        # CJK compatibility ideographs (U+F900–) come back NFC-normalized, so match on the normalized form.
        by_c = {unicodedata.normalize("NFC", c["literal"]): c for c in batch}
        prompt = "\n".join(
            f"{c['literal']} | ko: {','.join(readings(c, 'korean_h')) or '-'} | on: {','.join(readings(c, 'ja_on'))}"
            f" | kun: {','.join(readings(c, 'ja_kun'))} | en: {', '.join(meanings(c)[:5])}"
            for c in batch
        )
        recs = []
        for item in llm.call(KANJI_SYSTEM, prompt, KANJI_SCHEMA)["kanji"]:
            c = by_c.pop(unicodedata.normalize("NFC", item["c"]), None)
            if c is None:
                continue
            hunum = [h.strip() for h in item["hunum"] if HUNUM.match(h.strip())]
            recs.append({"c": c["literal"], "hunum": hunum, "m": args.model})
        store.add_many(recs)
        return len(recs), list(by_c.values())

    ok, failed, _ = _run(list(_chunk(todo, args.batch)), worker, args.workers)
    store.compact()
    print(f"translated {ok}, failed {len(failed)}")


def main(args):
    {"terms": translate_terms, "tags": translate_tags, "kanji": translate_kanji}[args.what](args)
