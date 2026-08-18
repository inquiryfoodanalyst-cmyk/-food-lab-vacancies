#!/usr/bin/env python3
"""
Fetches real-time food testing laboratory vacancy postings in India.

Sources (all via Google News RSS - no API keys required, ToS-safe):
  - General news/notification coverage of lab hiring
  - site: filters over major job portals (Naukri, Indeed, Shine, TimesJobs)
  - site: filters over LinkedIn job posts and public govt/FSSAI/NABL notices

Output: vacancies.json — a deduped, sorted list ready for the website widget.

Run manually:   python3 fetch_vacancies.py
Run on a schedule: see .github/workflows/update.yml (runs this every 3 hours)
"""

import json
import re
import time
import hashlib
import urllib.request
import urllib.parse
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

OUTPUT_FILE = "vacancies.json"
MAX_ITEMS = 150

# Each entry: (label shown in UI, google-news search query)
QUERIES = [
    ("News & Notices", 'food testing laboratory vacancy India'),
    ("News & Notices", 'food safety officer recruitment India'),
    ("FSSAI / Govt", 'FSSAI recruitment food analyst'),
    ("FSSAI / Govt", 'NABL food testing lab recruitment'),
    ("Job Portals", 'food testing laboratory vacancy site:naukri.com'),
    ("Job Portals", 'food analyst chemist job site:indeed.co.in'),
    ("Job Portals", 'food testing lab job site:shine.com'),
    ("Job Portals", 'food quality lab technician site:timesjobs.com'),
    ("LinkedIn", 'food testing laboratory hiring site:linkedin.com/jobs'),
    ("LinkedIn", 'food safety analyst hiring India site:linkedin.com/posts'),
    ("Twitter / X", 'food testing lab vacancy India site:twitter.com'),
    ("Twitter / X", 'food testing lab vacancy India site:x.com'),
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; VacancyBot/1.0)"}


def fetch_rss(query: str) -> str:
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": query, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"}
    )
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def parse_items(xml_bytes: bytes, category: str):
    items = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return items
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        source_el = item.find("source")
        source = source_el.text.strip() if source_el is not None and source_el.text else "Google News"
        if not title or not link:
            continue
        items.append(
            {
                "title": re.sub(r"\s+-\s+[^-]+$", "", title),  # strip trailing " - Source"
                "link": link,
                "source": source,
                "category": category,
                "published": pub_date,
            }
        )
    return items


def to_epoch(pub_date: str) -> float:
    if not pub_date:
        return 0
    try:
        dt = datetime.strptime(pub_date, "%a, %d %b %Y %H:%M:%S %Z")
        return dt.replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return 0


def dedupe(items):
    seen = set()
    out = []
    for it in items:
        key = hashlib.md5((it["title"].lower().strip()).encode()).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def main():
    all_items = []
    for category, query in QUERIES:
        try:
            xml_bytes = fetch_rss(query)
            all_items.extend(parse_items(xml_bytes, category))
        except Exception as e:
            print(f"[warn] query failed: {query!r} ({e})")
        time.sleep(1)  # be polite to Google's endpoint

    all_items = dedupe(all_items)
    all_items.sort(key=lambda x: to_epoch(x["published"]), reverse=True)
    all_items = all_items[:MAX_ITEMS]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(all_items),
        "items": all_items,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(all_items)} items to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
