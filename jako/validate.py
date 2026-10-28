"""Validate built dictionaries against Yomitan's JSON schemas, plus a few lookup smoke checks."""
import json
import re
import sys
import zipfile

from jsonschema.validators import validator_for

from .paths import DIST, SCHEMAS

BANK_SCHEMAS = {
    "term_bank": "dictionary-term-bank-v3-schema.json",
    "tag_bank": "dictionary-tag-bank-v3-schema.json",
    "kanji_bank": "dictionary-kanji-bank-v3-schema.json",
}
# term -> rule the row must carry, so conjugated forms (食べた, 勉強した) resolve
SMOKE_RULES = {"食べる": "v1", "行く": "v5", "勉強": "vs", "高い": "adj-i", "来る": "vk"}


def _validator(name):
    schema = json.loads((SCHEMAS / name).read_text())
    return validator_for(schema)(schema)


def validate_zip(path):
    errors = 0
    with zipfile.ZipFile(path) as z:
        for name in sorted(z.namelist()):
            if name == "index.json":
                v = _validator("dictionary-index-schema.json")
            elif m := re.match(r"(\w+_bank)_\d+\.json$", name):
                v = _validator(BANK_SCHEMAS[m.group(1)])
            else:
                continue
            for err in v.iter_errors(json.loads(z.read(name))):
                errors += 1
                if errors <= 20:
                    print(f"  {name}: {'/'.join(map(str, err.absolute_path))}: {err.message[:200]}")
        rows = [r for n in z.namelist() if n.startswith("term_bank_") for r in json.loads(z.read(n))]
    for term, rule in SMOKE_RULES.items():
        hits = [r for r in rows if r[0] == term]
        if rows and hits and not any(rule in r[3].split() for r in hits):
            errors += 1
            print(f"  smoke: {term} has no '{rule}' rule")
    print(f"{path.name}: {'OK' if not errors else f'{errors} errors'}")
    return errors


def main(args):
    zips = sorted(DIST.glob("*.zip"))
    if not zips:
        sys.exit("nothing in dist/ — run `python -m jako build` first")
    if sum(validate_zip(z) for z in zips):
        sys.exit(1)
