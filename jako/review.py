"""Dump a random sample of translations (optionally side by side with another store) for manual review."""
import random
from pathlib import Path

from . import jmdict
from .paths import REVIEW, TERMS_STORE
from .store import Store


def main(args):
    words = {e["id"]: e for e in jmdict.load()["words"]}
    store = Store(TERMS_STORE)
    other = Store(Path(args.against)) if args.against else None
    ids = [i for i, r in store.records.items() if (r["c"] == "low" or not args.low) and (not other or other.get(i))]
    random.Random(args.seed).shuffle(ids)
    out = []
    for i in sorted(ids[: args.n], key=int):
        e, r = words[i], store.get(i)
        kanji, kana = jmdict.display_forms(e)
        out.append(f"### {'・'.join(kanji[:2]) or kana[0]}【{kana[0]}】 #{i} conf={r['c']}")
        for n, s in enumerate(e["sense"]):
            line = f"{n + 1}. {'; '.join(g['text'] for g in s['gloss'])}\n   → {'; '.join(r['s'][n])}"
            if other:
                line += f"\n   ⇢ {'; '.join(other.get(i)['s'][n])}  ({other.get(i)['m']})"
            out.append(line)
        out.append("")
    REVIEW.mkdir(exist_ok=True)
    path = REVIEW / ("low.md" if args.low else "sample.md")
    path.write_text("\n".join(out))
    print(f"{min(len(ids), args.n)} entries → {path}")
