"""Print translation progress against the targets (common words, top-50k, kanji)."""
import json

from . import jmdict
from .paths import KANJI_STORE, KANJIDIC, TERMS_STORE
from .store import Store
from .translate import kanji_candidates

TARGET = 50049  # all common words (Sonnet) + the next 27,400 by frequency (Haiku)


def _pct(n, d):
    return f"{n:,} / {d:,} ({n / d:.1%})"


def main(args):
    words = jmdict.load()["words"]
    store = Store(TERMS_STORE)
    fresh = {e["id"] for e in words if (store.get(e["id"]) or {}).get("h") == jmdict.source_hash(e)}
    ranked = jmdict.rank(words)
    common = [e for e in ranked if jmdict.is_common(e)]
    top = ranked[:TARGET]
    kanji = Store(KANJI_STORE, key="c")
    cands = kanji_candidates(json.loads(KANJIDIC.read_text())["characters"])

    print(f"common words (sonnet): {_pct(sum(e['id'] in fresh for e in common), len(common))}")
    print(f"top {TARGET:,} target:   {_pct(sum(e['id'] in fresh for e in top), TARGET)}")
    print(f"all JMdict:            {_pct(len(fresh), len(words))}")
    print(f"stale (JMdict changed, will re-translate): {len(store.records) - len(fresh):,}")
    print(f"low confidence: {sum(1 for i in fresh if store.get(i)['c'] == 'low'):,}")
    print(f"kanji 훈음:            {_pct(sum(1 for c in cands if kanji.get(c['literal'])), len(cands))}")
