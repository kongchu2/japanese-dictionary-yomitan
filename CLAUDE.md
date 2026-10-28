# CLAUDE.md

This builds a Japanese→Korean dictionary for Yomitan: the JMdict structure plus Korean glosses translated by an LLM. User-facing docs are in README.md (Korean). Talk to the user in Korean.

## Hard constraints

- **Distributable sources only** (CC BY-SA family: JMdict, KANJIDIC2, Wiktionary, krdict). Never scrape Naver, Daum or other commercial dictionaries, not even "for hints".
- Translation backend is the **`claude` CLI on the user's subscription** (`jako/llm.py`). There is no API key. Your own session draws on the same account quota, so keep your own work lean while translations run.
- Python must stay 3.9-compatible: no `match`, no `X | Y` type unions.
- The GitHub repo `kongchu2/japanese-dictionary-yomitan` is **private**. Do not make it public unless the user asks.

## Layout

- `jako/`: CLI (`python -m jako <cmd>`): `fetch`, `translate {terms,tags,kanji}`, `build`, `validate`, `review`, `status`.
- `translations/`: the real asset, committed to git.
  - `terms.jsonl`: one line per JMdict entry, `{"id", "h": source hash, "s": [[ko glosses] per sense], "c": "high"|"low", "m": model}`.
  - If an entry's `h` no longer matches JMdict, it is stale: dropped from the build and re-translated on the next run.
  - `kanji.jsonl` holds 훈음. `tags.json` holds Korean labels for JMdict tags (hand-editable).
- `data/` (JMdict/KANJIDIC2 JSON, Yomitan schemas), `dist/` and `review/` are gitignored. Run `fetch` in a fresh checkout.
- `.github/workflows/release.yml`: daily build, plus on push to `translations/**` or `jako/**`. It validates, then creates a GitHub release only when `dist/content.sha256` differs from the latest release. CI never translates.

## Current task: finish step 3 (translate the top ~50k entries)

Check progress first: `python -m jako status`. On 2026-10-29: common words 69% (15,617 / 22,649), top-50k target 31%, kanji 100%.

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # fresh checkout only
.venv/bin/python -m jako fetch
claude -p --model haiku "say ok"        # verify the CLI is logged in before anything long
.venv/bin/python -m jako translate terms --common-only --model sonnet --workers 4
.venv/bin/python -m jako translate terms --limit 27400 --model haiku --workers 4
```

- **Order is decided.** Every JMdict "common" entry uses Sonnet. After that, the next 27,400 by frequency (wordfreq ranking in `jmdict.rank`) use Haiku.
  - `--limit` counts only untranslated entries, in rank order. Once common words are done, `--limit 27400` takes the next 27,400.
- **Runs are resumable and safe to interrupt.** Results are appended per batch.
- **Usage limit:** when the CLI reports the 5-hour/usage limit, the run stops cleanly and **exits with code 75**. Chain the commands with `&&` so the Haiku run does not start after a limit stop.
  - The limit message is matched by `_LIMIT_MARKERS` in `jako/llm.py`. If a new wording leaks through as repeated "batch failed" lines, kill the run and add the marker.
- Run long translations in the background. Don't poll; wait for the completion notification.

**After each run** (whether it finished or hit the limit):

```sh
.venv/bin/python -m jako build && .venv/bin/python -m jako validate
git add translations && git commit -m "Translate N more entries" && git push   # CI makes the release
```

End commit messages with the attribution line from the current session's system reminder, if there is one.

## Known issues / open work

- **~130 entries fail every time** (latest IDs are listed at the end of `review/common.log`; the file is gitignored, so re-run to see them). Cause not investigated.
  - Likely suspects: `_valid_senses` in `jako/translate.py` rejects glosses that contain kana/kanji, or the sense count doesn't match.
  - To debug: call `ClaudeCLI(...).call(TERMS_SYSTEM, jmdict.entry_prompt(e), TERMS_SCHEMA)` for one such entry and see which check fails.
  - Do not loosen the no-Japanese-script rule blindly. Glosses must be Hangul only.
- 21 kokuji (込, 枠, …) have empty 훈음, which is expected. Some kokuji 훈음 are invented (畑 → 화전 전, 峠 → 고개 상) and need a human check.
- About 2% of entries are `"c": "low"`. They render with a "신뢰도 낮음" note. `python -m jako review --low` dumps them for review.
- Not done yet: example sentences (Tatoeba) in the output; using krdict / kowiktionary as translation hints; Yomitan's in-app update check (works only once the repo is public).

## Translation prompt decisions (`TERMS_SYSTEM` in jako/translate.py)

These came from reviewing samples. Keep them:
- Translate the Japanese meaning; English glosses only mark sense boundaries.
- No fake Sino-Korean readings (勉強 → 공부, never 면강).
- No part-of-speech prefixes like "(조사)", because the dictionary already shows POS tags.
- Use real technical terms (corollary → 따름정리).
- Mark `low` only when the core meaning is uncertain.

Changing the prompt does **not** re-translate existing entries. If a change must apply retroactively, move `translations/terms.jsonl` aside and re-run. That costs many hours of quota, so ask the user first.
