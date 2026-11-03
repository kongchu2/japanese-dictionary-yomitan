# CLAUDE.md

This builds a Japanese→Korean dictionary for Yomitan: the JMdict structure plus Korean glosses translated by an LLM. User-facing docs are in README.md (Korean). Talk to the user in Korean.

## Hard constraints

- **Distributable sources only** (CC BY-SA family: JMdict, KANJIDIC2, Wiktionary, krdict). Never scrape Naver, Daum or other commercial dictionaries, not even "for hints".
- Translation backend is the **`claude` CLI on the user's subscription** (`jako/llm.py`). There is no API key. Your own session draws on the same account quota, so keep your own work lean while translations run.
- Python must stay 3.9-compatible: no `match`, no `X | Y` type unions.
- The GitHub repo `kongchu2/jmdict-ko` (renamed from japanese-dictionary-yomitan) is **private**. Do not make it public unless the user asks.

## Layout

- `jako/`: CLI (`python -m jako <cmd>`): `fetch`, `translate {terms,tags,kanji}`, `build`, `validate`, `review`, `status`.
- `translations/`: the real asset, committed to git.
  - `terms.jsonl`: one line per JMdict entry, `{"id", "h": source hash, "s": [[ko glosses] per sense], "c": "high"|"low", "m": model}`.
  - If an entry's `h` no longer matches JMdict, it is stale: dropped from the build and re-translated on the next run.
  - `kanji.jsonl` holds 훈음. `tags.json` holds Korean labels for JMdict tags (hand-editable).
- `data/` (JMdict/KANJIDIC2 JSON, Yomitan schemas), `dist/` and `review/` are gitignored. Run `fetch` in a fresh checkout.
- `.github/workflows/release.yml`: daily build, plus on push to `translations/**` or `jako/**`. It validates, then creates a GitHub release only when `dist/content.sha256` differs from the latest release. CI never translates.

## Status: every JMdict entry is translated

`python -m jako status` on 2026-11-03 (JMdict 3.6.2+20261102210542): all JMdict 219,009 / 219,009 (100%), common words 100% (Sonnet, except 4 that Sonnet kept failing and stay Haiku), kanji 100%, low confidence 12,091 (5.5%). Work happens on a `claude/...` branch and reaches `main` (and a release) through a PR.

## Keeping up with JMdict updates

JMdict (jmdict-simplified) publishes about once a week, and CI builds from the latest one. New entries and entries whose source changed (stale) are missing from the dictionary until translated. CI cannot translate, so run this after a JMdict update:

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # fresh checkout only
.venv/bin/python -m jako fetch
claude -p --model haiku "say ok"        # verify the CLI is logged in before anything long
.venv/bin/python -m jako translate terms --common-only --model sonnet --workers 4
.venv/bin/python -m jako translate terms --model haiku --workers 4
```

- **Order is decided.** Every JMdict "common" entry uses Sonnet; everything else uses Haiku. Run the Sonnet command first so common entries don't fall through to Haiku.
  - `--limit N` (optional) counts only untranslated entries, in rank order. Without it, every untranslated or stale entry is translated. A weekly update is usually under 100 entries and takes a few minutes.
- **Runs are resumable and safe to interrupt.** Results are appended per batch.
- **Usage limit:** when the CLI reports the 5-hour/usage limit, the run stops cleanly and **exits with code 75**. Chain the commands with `&&` so the Haiku run does not start after a limit stop.
  - The limit message is matched by `_LIMIT_MARKERS` in `jako/llm.py`. If a new wording leaks through as repeated "batch failed" lines, kill the run and add the marker.
- Run long translations in the background. Don't poll; wait for the completion notification.
- **Cloud sessions:** the agent proxy blocks the GitHub API, so `jako fetch` gets 403 on the jmdict-simplified `releases/latest` call. Direct release downloads work: take the newest tag from `git ls-remote --tags https://github.com/scriptin/jmdict-simplified` and download `https://github.com/scriptin/jmdict-simplified/releases/download/<tag>/{jmdict-examples-eng,kanjidic2-all}-<tag>.json.zip` into the paths `jako/fetch.py` uses (and write the tag to `SOURCE_VERSION`).

**After each run** (whether it finished or hit the limit):

```sh
.venv/bin/python -m jako build
git add translations && git commit -m "Translate N more entries" && git push   # merge to main; CI validates and makes the release
```

- `validate` checks the built zips against Yomitan's JSON schemas (from the yomitan repo) plus 5 conjugation smoke checks. It is this project's command, not Yomitan's.
- **Run it locally only when `jako/` (build code) or the schemas changed.** Translation-only changes don't alter the zip structure, and CI runs `validate` before every release anyway (a failed validate means no release).
- It uses `fastjsonschema` (~5 min for the full dictionary). When a file fails, it re-checks that file with `jsonschema` to list the errors, which takes a few extra minutes.

End commit messages with the attribution line from the current session's system reminder, if there is one.

## Known issues / open work

- **A few entries fail validation per run** (75 of 27,400 on the last Haiku run; all passed when re-run). Investigated 2026-10-29 by re-sending them one by one:
  - Most are random: the same entry passes on the next try. Just re-run the failing IDs (`--limit` picks them up first).
  - Persistent cause 1: the model adds hanja in parentheses (亡き → `고(故)`, 糸状 → `사상(絲狀)의`). `_valid_senses` rejects these, which is correct. The user decided **not** to strip the hanja automatically.
  - Persistent cause 2: the model splits one JMdict sense into several (春期, 仙道), so the sense count doesn't match.
  - Fixed: the model sometimes echoed ids as `"#123"` (how `entry_prompt` shows them), which failed a whole batch. `translate_terms` now strips the `#`.
  - Do not loosen the no-Japanese-script rule blindly. Glosses must be Hangul only.
- 21 kokuji (込, 枠, …) have empty 훈음, which is expected. The 음 of kokuji 훈음 was checked against Unihan `kHangul` (2026-11-03): 畑 전, 峠 상 etc. all match; 働 has no Unihan reading. The 훈 part is unverified. The user decided (2026-11-03) to leave kokuji 훈음 empty: Unihan and web searches confirm the 음 but no source gives a Korean 훈. Where KANJIDIC has a Korean reading, the build shows that reading alone (匂 → 내). The non-kokuji 曼 (끌 만), 湧 (물 솟을 용), 噛 (깨물 교) and 崚 (험준할 릉) were filled by hand (`"m": "manual"`).
- About 5.5% of entries (12,091) are `"c": "low"`; the rate rises with rank (3.1% in the top 50k, 7.2% at ranks 150k–200k). They render with a "신뢰도 낮음" note. `python -m jako review --low -n 2000` dumps them all to `review/low.md` (gitignored).
  - Typical topics: kana-only words (`uk`), archaic senses, abbreviations, Buddhist/historical terms, mahjong and go terms, species names.
  - A spot check found most of them acceptable. Real errors seen include fake Sino-Korean readings (一過 → 일과), wrong domain terms (下駄 in go → "덤 효과의 이득"), and loanword spelling (ドック → 독 rather than 도크).
  - Fixed 2026-11-03: "(고어)" on 169 senses JMdict doesn't tag `arch`/`obs`/`dated` removed; 21 glosses with English mixed in (시트belt, 저녁noon, …) hand-fixed; 13 duplicate glosses removed. Since 2026-11-03 `_valid_senses` also rejects lowercase English words (`_has_english` in `jako/translate.py`; acronyms, units, single letters, binomial names and quoted text pass). Two leaks it found were fixed by hand (盈虧 `기�häu`, 非行 `non`).
  - 49 multi-sense entries have the same gloss for every sense; most are correct in Korean (バス, 内科). The user chose to leave them.
- Not done yet: example sentences (Tatoeba) in the output; using krdict / kowiktionary as translation hints; Yomitan's in-app update check (works only once the repo is public).

## Translation prompt decisions (`TERMS_SYSTEM` in jako/translate.py)

These came from reviewing samples. Keep them:
- Translate the Japanese meaning; English glosses only mark sense boundaries.
- No fake Sino-Korean readings (勉強 → 공부, never 면강).
- No part-of-speech prefixes like "(조사)", because the dictionary already shows POS tags.
- Use real technical terms (corollary → 따름정리).
- Mark `low` only when the core meaning is uncertain.

Changing the prompt does **not** re-translate existing entries. If a change must apply retroactively, move `translations/terms.jsonl` aside and re-run. That costs many hours of quota, so ask the user first.
