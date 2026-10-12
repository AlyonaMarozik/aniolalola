#!/usr/bin/env python3
"""Publish one reviewed Sadzawka plant into the live catalog. No network or scheduling.

Usage: python scripts/publish_sadzawka_catalog.py --candidate path/to/reviewed.json
Run with a candidate whose fields have been checked against its exact product page.
"""
import argparse
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "catalog/exports/pilot-sadzawka.json"
WATER = re.compile(r"(?i)\b(nymphaea|nelumbo|nymphoides|pistia|lemna|salvinia|azolla|hydrocharis|eichhornia|stratiotes|myriophyllum|potamogeton|elodea|ceratophyllum)\b")

def normalized(name):
    return " ".join(unicodedata.normalize("NFKC", name).casefold()
                    .translate(str.maketrans({"‘": "'", "’": "'", "„": "'", "”": "'", '"': "'"})).split())

def publish(candidate, catalog):
    records = catalog["records"]
    name = candidate.get("botanical_name", "")
    source = candidate.get("source_url", "")
    if not name or not candidate.get("id") or not candidate.get("description"):
        raise ValueError("Missing required identity or description")
    if not candidate.get("traits") or not isinstance(candidate["traits"], dict):
        raise ValueError("Reviewed botanical traits are required")
    if candidate.get("source") != "sadzawka.pl" or urlparse(source).scheme != "https" or urlparse(source).hostname not in ("sadzawka.pl", "www.sadzawka.pl"):
        raise ValueError("Source must be an exact HTTPS Sadzawka product page")
    if WATER.search(name):
        raise ValueError("Water plant excluded")
    if any(p.get("id") == candidate["id"] or normalized(p.get("botanical_name", "")) == normalized(name)
           or p.get("source_url") == source for p in records):
        raise ValueError("Candidate already exists (ID, botanical name, or source URL)")
    img = candidate.get("image", {})
    if img.get("url"):
        parsed = urlparse(img["url"])
        if parsed.scheme != "https" or parsed.hostname not in ("sadzawka.pl", "www.sadzawka.pl"):
            raise ValueError("Image URL must point to Sadzawka over HTTPS")
    records.append(candidate)
    return catalog

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", required=True, type=Path)
    ap.add_argument("--catalog", default=LIVE, type=Path)
    args = ap.parse_args()
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    publish(candidate, catalog)
    args.catalog.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Published 1 reviewed botanical record: {candidate['botanical_name']}")

if __name__ == "__main__":
    main()
