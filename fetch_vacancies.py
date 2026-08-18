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
MAX_AGE_DAYS = 30  # drop anything older than this

# Each entry: (label shown in UI, google-news search query)
# Every query is phrased around hiring/recruitment terms specifically,
# to bias results toward postings rather than general news coverage.
QUERIES = [
    ("FSSAI / Govt", 'FSSAI recruitment food analyst vacancy'),
    ("FSSAI / Govt", 'NABL food testing lab recruitment vacancy'),
    ("FSSAI / Govt", 'food safety officer recruitment India vacancy'),
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

# Direct career pages of food testing labs / certification & inspection
# bodies. Each page is checked directly (not via Google) for signs of an
# active opening, since these are the most authoritative source.
LAB_CAREER_PAGES = [
    "https://qcin.org/work-with-us/",
    "https://www.indianspices.com/opportunities.html",
    "https://www.teaboard.gov.in/TEABOARDPAGE/MTQ=",
    "https://mpeda.gov.in/?page_id=1155",
    "https://apeda.gov.in/recruitment-appointment",
    "https://fssai.gov.in/jobs@fssai.php",
    "https://www.eicindia.gov.in/WebApp1/pages/menuInfo/recruitments.xhtml",
    "https://recruitmentcoffeeboard2025.in/",
    "http://careers.nddb.coop/SitePages/Career-Opportunities-Jobs.aspx",
    "https://dmi.gov.in/Recruitment.aspx",
    "https://ppqs.gov.in/en/internship",
    "https://abctechnolab.com/careers/",
    "https://accuratelaboratory.in/career/",
    "https://www.aeslabs.com/index.php/career/",
    "https://alexstewartindia.com/career/",
    "https://www.alsglobal.com/en/careers",
    "https://anaconlaboratories.com/careers/",
    "https://srigomuki.com/",
    "https://arbropharma.com/careers/",
    "https://ashwamedh.net/careers/",
    "https://ltfoods.com/career",
    "https://audenteslabs.com/",
    "https://avonfoodlab.com/careers/",
    "https://www.bureauveritas.co.in/working-bureau-veritas",
    "https://www.mettexlab.com/careers",
    "https://cultivatorphytolab.com/careers/",
    "https://www.delhitesthouse.com/",
    "https://www.einfrac.in/career",
    "https://ecogreenlabsindia.com/career/",
    "https://efrac.org/work-with-us/",
    "https://envirocarelabs.com/open-positions/",
    "https://envirocarelabs.com/jobs/",
    "https://www.equinoxlab.com/",
    "https://eurekaserv.com/careers/",
    "https://careers.eurofins.com/in",
    "https://farelabs.com/careers/",
    "https://fhhl.in/",
    "https://recruit.zohopublic.com/recruit/Portal.na?iframe=false&digest=90Y5ckZZcfEcDAzew9pW.XGAUnkE7bVo.a85bxdBEmQ-",
    "https://geochem.net.in/en/careers",
    "https://hthlabs.com/careers/",
    "https://www.ifl.in/careers/",
    "https://www.itclabs.com/career-with-us/",
    "https://www.intertek.com/careers/",
    "https://www.irclass.org/careers/",
    "https://kiitincubator.in/career/",
    "https://www.merieuxnutrisciences.com/in/careers-at-merieux-nutrisciences/",
    "https://www.multanilabs.com/Food-Testing",
    "https://ncml.com/career/",
    "http://www.piouslabs.com/job-vacancy/page-48899349",
    "https://www.sealab.in/index.php",
    "https://www.sgs.com/en/our-company/careers-at-sgs/job-opportunities",
    "https://www.shivaanalyticals.com/en/about/careers-at-shiva-analyticals",
    "https://www.shriraminstitute.org/career/",
    "https://smsla.global/careers-at-sms-labs/",
    "https://www.simalab.net/",
    "https://www.niist.res.in/opportunities-and-careers/permanent-positions",
    "https://www.niist.res.in/opportunities-and-careers/temporary-position",
    "https://www.tuv-nord.com/in/en/career-with-us/",
    "https://vimta.com/careers/",
]

# Known display names for the bigger/well-known organizations. Anything not
# listed here falls back to an auto-generated name from the domain.
KNOWN_NAMES = {
    "qcin.org": "Quality Council of India",
    "indianspices.com": "Spices Board India",
    "teaboard.gov.in": "Tea Board India",
    "mpeda.gov.in": "MPEDA",
    "apeda.gov.in": "APEDA",
    "fssai.gov.in": "FSSAI",
    "eicindia.gov.in": "Export Inspection Council",
    "recruitmentcoffeeboard2025.in": "Coffee Board",
    "nddb.coop": "NDDB",
    "dmi.gov.in": "Directorate of Marketing & Inspection",
    "ppqs.gov.in": "PPQS",
    "alsglobal.com": "ALS Global",
    "bureauveritas.co.in": "Bureau Veritas",
    "careers.eurofins.com": "Eurofins",
    "intertek.com": "Intertek",
    "irclass.org": "IRClass",
    "merieuxnutrisciences.com": "Merieux NutriSciences",
    "sgs.com": "SGS",
    "tuv-nord.com": "TUV Nord",
    "vimta.com": "Vimta Labs",
}


def display_name_for(url: str) -> str:
    netloc = urllib.parse.urlparse(url).netloc.lower()
    netloc = netloc[4:] if netloc.startswith("www.") else netloc
    for domain, name in KNOWN_NAMES.items():
        if domain in netloc:
            return name
    core = netloc.split(".")[0]
    core = re.sub(r"[-_]+", " ", core)
    return core.title()


# Phrases that indicate a career page currently shows active openings.
LAB_PAGE_POSITIVE = [
    "vacancy", "vacancies", "current opening", "current openings",
    "job opening", "job openings", "we are hiring", "we're hiring",
    "apply now", "apply online", "open position", "open positions",
    "career opportunit", "job opportunit", "walk-in", "walk in interview",
]

# Phrases that indicate there are explicitly NO current openings.
LAB_PAGE_NEGATIVE = [
    "no current openings", "no current vacancies", "no vacancies at this time",
    "no open positions", "currently no openings", "no openings available",
]


def fetch_lab_page(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()
    try:
        return raw.decode("utf-8", errors="ignore")
    except Exception:
        return raw.decode("latin-1", errors="ignore")


def check_lab_pages():
    items = []
    for url in LAB_CAREER_PAGES:
        try:
            html = fetch_lab_page(url).lower()
        except Exception as e:
            print(f"[warn] lab page failed: {url} ({e})")
            continue

        if any(neg in html for neg in LAB_PAGE_NEGATIVE):
            continue
        if not any(pos in html for pos in LAB_PAGE_POSITIVE):
            continue

        name = display_name_for(url)
        items.append(
            {
                "title": f"Openings currently listed — {name}",
                "link": url,
                "source": name,
                "category": "Lab Career Pages",
                "published": datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT"),
            }
        )
        time.sleep(0.5)
    return items

# A result's title must contain at least one of these to be treated as an
# actual job posting...
INCLUDE_KEYWORDS = [
    "vacancy", "vacancies", "recruitment", "hiring", "walk-in", "walk in",
    "job opening", "job openings", "apply now", "recruit", "post of",
    "posts of", "requires", "wanted", "career", "openings", "job alert",
]

# ...and must NOT contain any of these, which signal it's ordinary news
# coverage rather than a hiring notice.
EXCLUDE_KEYWORDS = [
    "raid", "seized", "seizure", "fine", "penalty", "penalised", "penalized",
    "banned", "ban on", "warns", "warning", "adulterat", "contamina",
    "poisoning", "shut down", "shuts down", "license cancel", "fssai license",
    "food safety index", "inspection drive", "notice to", "show cause",
    "court", "case against", "fir against", "arrested", "fake food",
]


def is_relevant(title: str) -> bool:
    t = title.lower()
    if any(bad in t for bad in EXCLUDE_KEYWORDS):
        return False
    return any(good in t for good in INCLUDE_KEYWORDS)


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
        if not title or not link or not is_relevant(title):
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


def is_within_age_limit(pub_date: str, max_age_days: int) -> bool:
    epoch = to_epoch(pub_date)
    if epoch == 0:
        # If we can't parse a date, keep it rather than silently dropping it.
        return True
    age_seconds = time.time() - epoch
    return age_seconds <= max_age_days * 86400


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

    print("Checking direct lab career pages...")
    all_items.extend(check_lab_pages())

    all_items = dedupe(all_items)
    all_items = [it for it in all_items if is_within_age_limit(it["published"], MAX_AGE_DAYS)]
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
