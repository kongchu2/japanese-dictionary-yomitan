from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
SCHEMAS = ROOT / "data" / "schemas"
TRANSLATIONS = ROOT / "translations"
DIST = ROOT / "dist"
REVIEW = ROOT / "review"

JMDICT = RAW / "jmdict.json"
KANJIDIC = RAW / "kanjidic2.json"
SOURCE_VERSION = RAW / "VERSION"

TERMS_STORE = TRANSLATIONS / "terms.jsonl"
KANJI_STORE = TRANSLATIONS / "kanji.jsonl"
TAGS_FILE = TRANSLATIONS / "tags.json"

REPO = "kongchu2/japanese-dictionary-yomitan"
RELEASE_URL = f"https://github.com/{REPO}/releases/latest/download"
