"""Download JMdict/KANJIDIC2 (jmdict-simplified JSON) and the Yomitan dictionary schemas."""
import io
import json
import urllib.request
import zipfile

from .paths import JMDICT, KANJIDIC, RAW, SCHEMAS, SOURCE_VERSION

JMDICT_SIMPLIFIED = "https://api.github.com/repos/scriptin/jmdict-simplified/releases/latest"
SCHEMA_BASE = "https://raw.githubusercontent.com/yomidevs/yomitan/master/ext/data/schemas"
SCHEMA_FILES = [
    "dictionary-index-schema.json",
    "dictionary-term-bank-v3-schema.json",
    "dictionary-tag-bank-v3-schema.json",
    "dictionary-kanji-bank-v3-schema.json",
]
# asset name prefix -> local file
ASSETS = {
    "jmdict-examples-eng-": JMDICT,
    "kanjidic2-all-": KANJIDIC,
}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "jako-builder"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def fetch_sources():
    RAW.mkdir(parents=True, exist_ok=True)
    release = json.loads(_get(JMDICT_SIMPLIFIED))
    tag = release["tag_name"]
    if SOURCE_VERSION.exists() and SOURCE_VERSION.read_text().strip() == tag and all(p.exists() for p in ASSETS.values()):
        print(f"jmdict-simplified {tag}: already up to date")
        return
    for prefix, dest in ASSETS.items():
        asset = next(a for a in release["assets"] if a["name"].startswith(prefix) and a["name"].endswith(".json.zip"))
        print(f"downloading {asset['name']}")
        with zipfile.ZipFile(io.BytesIO(_get(asset["browser_download_url"]))) as z:
            (name,) = [n for n in z.namelist() if n.endswith(".json")]
            dest.write_bytes(z.read(name))
    SOURCE_VERSION.write_text(tag + "\n")
    print(f"jmdict-simplified {tag}")


def fetch_schemas():
    SCHEMAS.mkdir(parents=True, exist_ok=True)
    for name in SCHEMA_FILES:
        (SCHEMAS / name).write_bytes(_get(f"{SCHEMA_BASE}/{name}"))


def main(args):
    fetch_sources()
    fetch_schemas()
