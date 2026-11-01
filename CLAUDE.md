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

## Status: step 3 is done (top ~50k entries translated)

`python -m jako status` on 2026-10-29: common words 100% (22,649), top-50,049 target 100%, all JMdict 22.9%, kanji 100%, low confidence 1,538. Translations are on branch `claude/nice-babbage-ldd0ue`; CI releases only from `main`, so nothing is released until that branch is merged.

Re-running a translation (after a JMdict update makes entries stale, or to extend coverage):

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # fresh checkout only
.venv/bin/python -m jako fetch
claude -p --model haiku "say ok"        # verify the CLI is logged in before anything long
.venv/bin/python -m jako translate terms --common-only --model sonnet --workers 4
.venv/bin/python -m jako translate terms --limit N --model haiku --workers 4
```

- **Order is decided.** Every JMdict "common" entry uses Sonnet. After that, entries by frequency (wordfreq ranking in `jmdict.rank`) use Haiku; the target is the top 50,049 (`TARGET` in `jako/status.py`).
  - `--limit` counts only untranslated entries, in rank order (including common ones a Sonnet run failed on, which then go to Haiku). To stay inside the target, set N to the number of untranslated entries in the top 50,049, not a fixed 27,400.
- **Runs are resumable and safe to interrupt.** Results are appended per batch.
- **Usage limit:** when the CLI reports the 5-hour/usage limit, the run stops cleanly and **exits with code 75**. Chain the commands with `&&` so the Haiku run does not start after a limit stop.
  - The limit message is matched by `_LIMIT_MARKERS` in `jako/llm.py`. If a new wording leaks through as repeated "batch failed" lines, kill the run and add the marker.
- Run long translations in the background. Don't poll; wait for the completion notification.
- **Cloud sessions:** the agent proxy blocks the GitHub API, so `jako fetch` gets 403 on the jmdict-simplified `releases/latest` call. Direct release downloads work: take the newest tag from `git ls-remote --tags https://github.com/scriptin/jmdict-simplified` and download `https://github.com/scriptin/jmdict-simplified/releases/download/<tag>/{jmdict-examples-eng,kanjidic2-all}-<tag>.json.zip` into the paths `jako/fetch.py` uses (and write the tag to `SOURCE_VERSION`).

**After each run** (whether it finished or hit the limit):

```sh
.venv/bin/python -m jako build && .venv/bin/python -m jako validate
git add translations && git commit -m "Translate N more entries" && git push   # CI makes the release
```

End commit messages with the attribution line from the current session's system reminder, if there is one.

## Known issues / open work

- **A few entries fail validation per run** (75 of 27,400 on the last Haiku run; all passed when re-run). Investigated 2026-10-29 by re-sending them one by one:
  - Most are random: the same entry passes on the next try. Just re-run the failing IDs (`--limit` picks them up first).
  - Persistent cause 1: the model adds hanja in parentheses (亡き → `고(故)`, 糸状 → `사상(絲狀)의`). `_valid_senses` rejects these, which is correct. The user decided **not** to strip the hanja automatically.
  - Persistent cause 2: the model splits one JMdict sense into several (春期, 仙道), so the sense count doesn't match.
  - Fixed: the model sometimes echoed ids as `"#123"` (how `entry_prompt` shows them), which failed a whole batch. `translate_terms` now strips the `#`.
  - Do not loosen the no-Japanese-script rule blindly. Glosses must be Hangul only.
  - Still untranslated after the ranks 50,050–80,049 run (2026-11-01), not investigated: 2851823 郡家, 1180200 押し詰まる, 1183430 温色, 1210910 勧化. All have one sense whose glosses pack several meanings together, so the sense-split cause is likely.
- 21 kokuji (込, 枠, …) have empty 훈음, which is expected. Some kokuji 훈음 are invented (畑 → 화전 전, 峠 → 고개 상) and need a human check.
- About 3% of entries (1,538) are `"c": "low"`: 1,021 Haiku, 517 Sonnet, 518 of them common words. They render with a "신뢰도 낮음" note. `python -m jako review --low -n 2000` dumps them all to `review/low.md` (gitignored).
  - Typical topics: kana-only words (`uk`), archaic senses, abbreviations, Buddhist/historical terms, mahjong and go terms, species names.
  - A spot check found most of them acceptable. Real errors seen include fake Sino-Korean readings (一過 → 일과), wrong domain terms (下駄 in go → "덤 효과의 이득"), and loanword spelling (ドック → 독 rather than 도크).
  - 49 entries put "(고어)" on senses JMdict doesn't tag `arch`/`obs`/`dated` (e.g. おっかない sense 2).
- Not done yet: example sentences (Tatoeba) in the output; using krdict / kowiktionary as translation hints; Yomitan's in-app update check (works only once the repo is public).

## Translation prompt decisions (`TERMS_SYSTEM` in jako/translate.py)

These came from reviewing samples. Keep them:
- Translate the Japanese meaning; English glosses only mark sense boundaries.
- No fake Sino-Korean readings (勉強 → 공부, never 면강).
- No part-of-speech prefixes like "(조사)", because the dictionary already shows POS tags.
- Use real technical terms (corollary → 따름정리).
- Mark `low` only when the core meaning is uncertain.

Changing the prompt does **not** re-translate existing entries. If a change must apply retroactively, move `translations/terms.jsonl` aside and re-run. That costs many hours of quota, so ask the user first.
