#!/usr/bin/env python3
"""Collect direct remote Sadzawka image URLs, one plant per iteration.

Never downloads/stores photos, never guesses filenames, never overwrites existing URLs.
Run: python scripts/collect_sadzawka_photos.py --limit 1
"""
import json
import argparse
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog/exports/pilot-sadzawka.json"
LOG = ROOT / "catalog/exports/photo-collection-log.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; GardenCatalogPhotoCollector/1.0)"}
IMAGE_RE = re.compile(r"\.(?:jpe?g|png|webp)(?:[?#]|$)", re.I)
SADZAWKA_HOSTS = ("sadzawka.pl", "www.sadzawka.pl")


class Images(HTMLParser):
    def __init__(self):
        super().__init__()
        self.candidates = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and (a.get("property") in ("og:image", "og:image:secure_url") or a.get("name") == "twitter:image"):
            self.candidates.append(("meta", a.get("content", "")))
        if tag == "img":
            for key in ("data-src", "data-original", "data-lazy", "src"):
                if a.get(key):
                    self.candidates.append(("img", a[key]))
            if a.get("srcset"):
                self.candidates.extend(("img", part.strip().split(" ")[0]) for part in a["srcset"].split(","))


def request(url, method="GET"):
    req = Request(url, headers=HEADERS, method=method)
    return urlopen(req, timeout=20)


def valid_image(url):
    try:
        with request(url, "HEAD") as response:
            if response.headers.get("Content-Type", "").lower().startswith("image/"):
                return True
    except (HTTPError, URLError, TimeoutError, OSError):
        pass
    try:
        with request(url) as response:
            return response.headers.get("Content-Type", "").lower().startswith("image/")
    except (HTTPError, URLError, TimeoutError, OSError):
        return False


def candidates(html, page):
    parser = Images()
    parser.feed(html)
    scored = []
    for kind, raw in parser.candidates:
        url = urljoin(page, raw.strip())
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc not in SADZAWKA_HOSTS:
            continue
        if not IMAGE_RE.search(parsed.path) and "/environment/cache/images/" not in parsed.path:
            continue
        score = (100 if kind == "meta" else 0) + (50 if "productGfx_" in url else 0) + (20 if "/environment/cache/images/" in url else 0)
        scored.append((score, url))
    seen = set()
    for _, url in sorted(scored, reverse=True):
        if url not in seen:
            seen.add(url)
            yield url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of missing Sadzawka photos to process (0=all)")
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit cannot be negative")
    doc = json.loads(CATALOG.read_text(encoding="utf-8"))
    results = []
    changed = 0
    processed = 0
    for item in doc["records"]:
        if item.get("image", {}).get("url"):
            continue
        page = item.get("source_url")
        if urlparse(page or "").netloc not in SADZAWKA_HOSTS:
            continue
        if args.limit and processed >= args.limit:
            break
        processed += 1
        name = item["botanical_name"]
        entry = {"id": item["id"], "name": name, "source_url": page}
        try:
            with request(page) as response:
                html = response.read().decode("utf-8", "replace")
            options = list(candidates(html, page))
            entry["candidates"] = len(options)
            # Prefer the product-specific meta image over related product images.
            meta_parser = Images()
            meta_parser.feed(html)
            metas = {urljoin(page, raw) for kind, raw in meta_parser.candidates if kind == "meta"}
            chosen = None
            for url in options:
                if url in metas and valid_image(url):
                    chosen = url
                    break
            if not chosen:
                product_images = [url for url in options if "productGfx_" in url]
                if len(product_images) == 1 and valid_image(product_images[0]):
                    chosen = product_images[0]
            if chosen:
                item["image"] = {
                    "url": chosen,
                    "status": "verified_remote_image",
                    "source_url": page
                }
                entry["status"] = "added"
                entry["image_url"] = chosen
                changed += 1
            else:
                entry["status"] = "no_unambiguous_verified_image"
        except Exception as exc:
            entry["status"] = "error"
            entry["error"] = str(exc)[:300]
        results.append(entry)
        print(f"{name}: {entry['status']}", flush=True)
        time.sleep(1)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(json.dumps({"added": changed, "results": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if changed:
        CATALOG.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Added {changed} verified remote photo URLs. See {LOG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
