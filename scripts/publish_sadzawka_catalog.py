#!/usr/bin/env python3
"""Publish a validated Sadzawka batch with one JSON write, no Git commits.

Run: python scripts/publish_sadzawka_catalog.py --batch reviewed.json --dry-run
Then: python scripts/publish_sadzawka_catalog.py --batch reviewed.json
Commit the updated catalog JSON once after review.
"""
import argparse
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "catalog/exports/pilot-sadzawka.json"
HOSTS = {"sadzawka.pl", "www.sadzawka.pl"}
WATER = re.compile(r"(?i)\b(nymphaea|nelumbo|nymphoides|pistia|lemna|salvinia|azolla|hydrocharis|eichhornia|stratiotes|myriophyllum|potamogeton|elodea|ceratophyllum)\b")
ALLOWED_TRAITS = {
    "family", "origin", "height_cm", "height_cm_min", "height_cm_max",
    "width_cm", "width_cm_min", "width_cm_max", "spread_cm", "habit", "growth",
    "foliage", "foliage_type", "evergreen", "flowering", "flowering_period",
    "flower_color", "flower_shape", "bloom", "light", "soil", "soil_ph",
    "soil_structure", "drainage", "moisture", "water", "watering", "wind",
    "hardiness_zone", "frost_resistance", "winter_care", "recommended_uses",
    "leaf_length_cm", "leaf_width_cm", "care", "fragrance", "root_system"
}

def normalized(name):
    name = unicodedata.normalize("NFKC", str(name or ""))
    name = name.translate(str.maketrans({"‘": "'", "’": "'", "„": "'", "”": "'", '"': "'"}))
    return " ".join(name.casefold().split())

def validate(candidate):
    if not isinstance(candidate, dict):
        raise ValueError("Batch item must be an object")
    name = candidate.get("botanical_name")
    if not isinstance(name, str) or not name.strip() or not candidate.get("id"):
        raise ValueError("Missing botanical_name or id")
    description = candidate.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ValueError(f"Missing short description: {name}")
    if WATER.search(name):
        raise ValueError(f"Excluded aquatic plant: {name}")
    source = urlparse(candidate.get("source_url", ""))
    if candidate.get("source") != "sadzawka.pl" or source.scheme != "https" or source.hostname not in HOSTS:
        raise ValueError(f"Invalid Sadzawka product source: {name}")
    traits = candidate.get("traits")
    if not isinstance(traits, dict) or not traits:
        raise ValueError(f"Missing reviewed botanical characteristics: {name}")
    unrecognized = set(traits) - ALLOWED_TRAITS
    if unrecognized:
        raise ValueError(f"Unknown or retail trait fields for {name}: {sorted(unrecognized)}")
    if not any(k in traits for k in ("height_cm", "height_cm_min", "height_cm_max", "width_cm", "width_cm_max", "habit")):
        raise ValueError(f"Missing dimensions or habit: {name}")
    if not any(k in traits for k in ("light", "soil", "moisture", "drainage")):
        raise ValueError(f"Missing growing conditions: {name}")
    img = candidate.get("image") or {}
    if not isinstance(img, dict):
        raise ValueError(f"Bad image data: {name}")
    if img.get("url"):
        u = urlparse(img["url"])
        if u.scheme != "https" or u.hostname not in HOSTS:
            raise ValueError(f"Invalid image host: {name}")
    return candidate

def publish_batch(batch, catalog):
    """Validate whole batch before mutating anything; never overwrite old cards."""
    if not isinstance(batch, list) or not batch:
        raise ValueError("Batch must be a non-empty array")
    records = catalog["records"]
    ids = {r.get("id") for r in records}
    names = {normalized(r.get("botanical_name")) for r in records}
    urls = {r.get("source_url") for r in records}
    checked = []
    for item in batch:
        p = validate(item)
        n = normalized(p["botanical_name"])
        if p["id"] in ids or n in names or p["source_url"] in urls:
            raise ValueError(f"Duplicate card: {p['botanical_name']}")
        ids.add(p["id"]); names.add(n); urls.add(p["source_url"]); checked.append(p)
    return {**catalog, "records": [*records, *checked]}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True, type=Path, help="Reviewed JSON array or object with records list")
    ap.add_argument("--catalog", type=Path, default=LIVE)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    data = json.loads(args.batch.read_text(encoding="utf-8"))
    batch = data.get("records") if isinstance(data, dict) else data
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    updated = publish_batch(batch, catalog)
    count = len(updated["records"]) - len(catalog["records"])
    if not args.dry_run:
        args.catalog.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix=".sadzawka-", dir=args.catalog.parent, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump(updated, out, ensure_ascii=False, indent=2)
                out.write("\n")
            os.replace(temp, args.catalog)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
    print(f"{'Validated' if args.dry_run else 'Published'} {count} reviewed plants; total {len(updated['records'])}")

if __name__ == "__main__":
    main()
