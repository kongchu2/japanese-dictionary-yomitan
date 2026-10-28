"""Build the Yomitan dictionaries (JMdict-ko term dictionary, KANJIDIC-ko kanji dictionary)."""
import hashlib
import json
import zipfile
from datetime import datetime, timezone

from . import jmdict
from .paths import DIST, KANJI_STORE, KANJIDIC, RELEASE_URL, REPO, TAGS_FILE, TERMS_STORE
from .store import Store
from .translate import kanji_candidates, readings

BANK_SIZE = 10000
AUTHOR = "kongchu2"
REPO_URL = f"https://github.com/{REPO}"

STYLES = """\
[data-sc-jako="tag"] {
  font-size: 0.75em; font-weight: bold; padding: 0.1em 0.35em; margin-right: 0.3em;
  border-radius: 0.3em; background-color: #5a5a5a; color: #fff; vertical-align: text-bottom;
}
[data-sc-kind="misc"] { background-color: #8a5a00; }
[data-sc-jako="xref"], [data-sc-jako="note"] { font-size: 0.85em; opacity: 0.8; }
[data-sc-jako="en"] { font-size: 0.85em; opacity: 0.75; margin-top: 0.3em; }
[data-sc-jako="en"] ol { margin: 0; }
"""


def _revision():
    return datetime.now(timezone.utc).strftime("%Y.%m.%d.%H%M")


def _index(title, name, description, attribution, sequenced):
    return {
        "title": title,
        "revision": _revision(),
        "format": 3,
        "sequenced": sequenced,
        "author": AUTHOR,
        "url": REPO_URL,
        "description": description,
        "attribution": attribution,
        "sourceLanguage": "ja",
        "targetLanguage": "ko",
        "isUpdatable": True,
        "indexUrl": f"{RELEASE_URL}/{name}-index.json",
        "downloadUrl": f"{RELEASE_URL}/{name}.zip",
    }


def _write_zip(name, index, banks, extra=None):
    """banks: {"term_bank": rows, ...}; returns sha256 of the content (index excluded)."""
    DIST.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with zipfile.ZipFile(DIST / f"{name}.zip", "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("index.json", json.dumps(index, ensure_ascii=False, indent=1))
        for bank, rows in banks.items():
            for n in range(0, max(len(rows), 1), BANK_SIZE):
                body = json.dumps(rows[n : n + BANK_SIZE], ensure_ascii=False, separators=(",", ":"))
                z.writestr(f"{bank}_{n // BANK_SIZE + 1}.json", body)
                digest.update(body.encode())
        for fname, body in (extra or {}).items():
            z.writestr(fname, body)
            digest.update(body.encode())
    (DIST / f"{name}-index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1))
    return digest.hexdigest()


class TagNames:
    """JMdict tag code -> Korean short label used as the Yomitan tag name."""

    def __init__(self, jmdict_tags):
        self.ko = json.loads(TAGS_FILE.read_text()) if TAGS_FILE.exists() else {}
        self.en = jmdict_tags
        self.used = {}  # tag name -> notes

    def short(self, code):
        return self.ko.get(code, {}).get("short") or code

    def long(self, code):
        return self.ko.get(code, {}).get("long") or self.en.get(code, code)

    def use(self, code):
        name = self.short(code)
        self.used.setdefault(name, self.long(code))
        return name


def _tag_span(tags, code, kind="tag"):
    data = {"jako": kind} if kind == "tag" else {"jako": "tag", "kind": kind}
    return {"tag": "span", "data": data, "title": tags.long(code), "content": tags.short(code)}


def _xref(related):
    links = []
    for ref in related:
        word = ref[0]
        label = f"{ref[0]}【{ref[1]}】" if len(ref) > 1 and isinstance(ref[1], str) else ref[0]
        if links:
            links.append("・")
        links.append({"tag": "a", "href": f"?query={word}&wildcards=off", "content": label})
    return {"tag": "div", "data": {"jako": "xref"}, "content": ["→ "] + links}


def _render(entry, idx, tr, tags):
    senses = entry["sense"]
    items, prev_pos = [], None
    for i in idx:
        s = senses[i]
        parts = []
        if s["partOfSpeech"] != prev_pos:
            parts += [_tag_span(tags, p) for p in s["partOfSpeech"]]
            prev_pos = s["partOfSpeech"]
        parts += [_tag_span(tags, t, "misc") for t in s["misc"] + s["field"] + s["dialect"]]
        if tr:
            parts.append({"tag": "span", "lang": "ko", "content": "; ".join(tr["s"][i])})
        else:
            parts.append({"tag": "span", "lang": "en", "content": "; ".join(g["text"] for g in s["gloss"])})
        if s["related"]:
            parts.append(_xref(s["related"]))
        items.append(parts)

    if len(items) == 1:
        content = [{"tag": "div", "content": items[0]}]
    else:
        content = [{"tag": "ol", "content": [{"tag": "li", "content": p} for p in items]}]
    if tr is None:
        content.append({"tag": "div", "data": {"jako": "note"}, "content": "※ 아직 번역되지 않은 항목 (영어 원문)"})
    elif tr["c"] == "low":
        content.append({"tag": "div", "data": {"jako": "note"}, "content": "※ 자동 번역 신뢰도 낮음 — 영어 원문을 확인하세요"})
    if tr:
        en = [{"tag": "li", "content": "; ".join(g["text"] for g in senses[i]["gloss"])} for i in idx]
        content.append({
            "tag": "details",
            "data": {"jako": "en"},
            "content": [{"tag": "summary", "content": "영어 원문 (JMdict)"}, {"tag": "ol", "lang": "en", "content": en}],
        })
    return {"type": "structured-content", "content": content}


def build_terms(include_untranslated=False):
    data = jmdict.load()
    store = Store(TERMS_STORE)
    tags = TagNames(data["tags"])
    star = "★"
    rows, n_entries = [], 0
    for e in data["words"]:
        tr = store.get(e["id"])
        if tr and tr["h"] != jmdict.source_hash(e):
            tr = None  # JMdict changed this entry since it was translated
        if tr is None and not include_untranslated:
            continue
        n_entries += 1
        for k, r in jmdict.headwords(e):
            idx = jmdict.sense_indices(e, k, r)
            if not idx:
                continue
            form = k or r
            rules = sorted({jmdict.rule_of(p) for i in idx for p in e["sense"][i]["partOfSpeech"]} - {None})
            form_tags = (k["tags"] if k else []) + r["tags"]
            score = (10 if form["common"] else 0) - (10 if set(form_tags) & jmdict.DISPREFERRED else 0)
            term_tags = ([star] if form["common"] else []) + [tags.use(t) for t in form_tags]
            rows.append([
                form["text"],
                r["text"] if k else "",
                "",
                " ".join(rules),
                score,
                [_render(e, idx, tr, tags)],
                int(e["id"]),
                " ".join(term_tags),
            ])
    tag_rows = [[star, "popular", -10, "자주 쓰이는 말 (JMdict 상용어)", 10]]
    tag_rows += [[name, "", 0, notes, 0] for name, notes in sorted(tags.used.items())]
    index = _index(
        "JMdict-ko",
        "jmdict-ko",
        f"JMdict 기반 일한사전. 한국어 뜻은 LLM 번역 (JMdict {data['dictDate']}).",
        "JMdict © Electronic Dictionary Research and Development Group (EDRDG), CC BY-SA 4.0. "
        "Korean translations derived from JMdict, CC BY-SA 4.0.",
        sequenced=True,
    )
    digest = _write_zip("jmdict-ko", index, {"term_bank": rows, "tag_bank": tag_rows}, {"styles.css": STYLES})
    print(f"jmdict-ko: {n_entries} entries, {len(rows)} rows")
    return digest


def build_kanji():
    chars = json.loads(KANJIDIC.read_text())["characters"]
    store = Store(KANJI_STORE, key="c")
    wanted = {c["literal"] for c in kanji_candidates(chars)}
    rows = []
    for c in chars:
        ko = readings(c, "korean_h")
        rec = store.get(c["literal"])
        hunum = rec["hunum"] if rec else []
        if not (hunum or ko):
            continue
        misc = c["misc"]
        stats = {"ko": ", ".join(ko) or "-", "strokes": str(misc["strokeCounts"][0])}
        if misc.get("grade"):
            stats["grade"] = str(misc["grade"])
        if misc.get("frequency"):
            stats["freq"] = str(misc["frequency"])
        if misc.get("jlptLevel"):
            stats["jlpt"] = str(misc["jlptLevel"])
        grade = misc.get("grade") or 0
        tag = "상용" if 1 <= grade <= 8 else "인명용" if grade >= 9 else ""
        rows.append([
            c["literal"],
            " ".join(readings(c, "ja_on")),
            " ".join(readings(c, "ja_kun")),
            tag,
            hunum or ko,
            stats,
        ])
    tag_rows = [
        ["상용", "frequent", 0, "상용한자 (常用漢字)", 0],
        ["인명용", "frequent", 0, "인명용 한자 (人名用漢字)", 0],
        ["ko", "misc", 0, "한국 한자음", 0],
        ["strokes", "misc", 1, "획수", 0],
        ["grade", "misc", 2, "학년 (1–6 교육한자, 8 상용, 9–10 인명용)", 0],
        ["freq", "misc", 3, "신문 빈도 순위", 0],
        ["jlpt", "misc", 4, "구 JLPT 급수", 0],
    ]
    index = _index(
        "KANJIDIC-ko",
        "kanjidic-ko",
        f"KANJIDIC2 기반 한자 사전. 한국 한자 훈음 수록 ({sum(1 for r in rows if r[0] in wanted)}자 훈음 보강).",
        "KANJIDIC2 © Electronic Dictionary Research and Development Group (EDRDG), CC BY-SA 4.0. "
        "Korean 훈음 derived from KANJIDIC2, CC BY-SA 4.0.",
        sequenced=False,
    )
    digest = _write_zip("kanjidic-ko", index, {"kanji_bank": rows, "tag_bank": tag_rows})
    print(f"kanjidic-ko: {len(rows)} kanji, {sum(1 for r in rows if store.get(r[0]))} with 훈음")
    return digest


def main(args):
    digests = {"jmdict-ko": build_terms(args.include_untranslated), "kanjidic-ko": build_kanji()}
    (DIST / "content.sha256").write_text("".join(f"{v}  {k}\n" for k, v in digests.items()))
