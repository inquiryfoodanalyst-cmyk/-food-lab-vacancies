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
FIRST_SEEN_FILE = "first_seen.json"
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
# Deliberately broad — a career page that loads successfully and isn't
# explicitly saying "no openings" is treated as worth listing, since
# under-showing is worse here than over-showing (the person can always
# click through to check).
LAB_PAGE_POSITIVE = [
    "vacancy", "vacancies", "current opening", "current openings",
    "job opening", "job openings", "we are hiring", "we're hiring",
    "apply now", "apply online", "open position", "open positions",
    "career opportunit", "job opportunit", "walk-in", "walk in interview",
    "career", "careers", "job", "jobs", "position", "positions",
    "recruitment", "recruit", "opportunit", "join us", "join our team",
    "current requirement", "requirement", "employment", "work with us",
    "internship", "apply", "opening",
]

# Phrases that indicate there are explicitly NO current openings.
LAB_PAGE_NEGATIVE = [
    "no current openings", "no current vacancies", "no vacancies at this time",
    "no open positions", "currently no openings", "no openings available",
    "no positions available", "no jobs available", "not hiring at this time",
]


def fetch_lab_page(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()
    try:
        return raw.decode("utf-8", errors="ignore")
    except Exception:
        return raw.decode("latin-1", errors="ignore")


# Words that suggest a line of text is actually a job title, not just
# mention of "careers" in a nav menu or footer.
JOB_TITLE_HINTS = [
    "analyst", "chemist", "technician", "officer", "executive", "engineer",
    "supervisor", "manager", "coordinator", "trainee", "intern",
    "microbiologist", "scientist", "assistant", "associate", "specialist",
    "inspector", "auditor", "lab technician", "sample collector",
    "chemist trainee", "quality analyst", "quality executive",
    "quality officer", "quality manager", "quality engineer",
    "qa executive", "qa officer", "qa manager", "qc executive",
    "qc officer", "qc manager", "qc chemist", "food safety officer",
]

# Boilerplate that shows up in nav/footer text and should never be treated
# as a job title even if it happens to contain a hint word.
JUNK_LINE_MARKERS = [
    "cookie", "privacy", "terms of", "©", "all rights reserved",
    "subscribe", "newsletter", "follow us", "contact us", "sitemap",
    "javascript", "please enable",
]


def extract_job_snippets(html: str, max_snippets: int = 3):
    """Best-effort extraction of individual job-title-looking lines from a
    career page. Works well on server-rendered listing pages; on JS-rendered
    (React/Angular) pages it will typically find nothing, which is fine —
    the caller falls back to a generic 'openings listed' item."""
    # Pull anchor text first — job titles are very often clickable links.
    anchor_texts = re.findall(r"<a\b[^>]*>(.*?)</a>", html, flags=re.I | re.S)

    # Strip remaining tags/scripts/styles to get plain body text too.
    no_script = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    plain = re.sub(r"<[^>]+>", "\n", no_script)
    plain_lines = plain.splitlines()

    candidates = []
    for raw_line in anchor_texts + plain_lines:
        line = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw_line)).strip()
        if not (6 <= len(line) <= 90):
            continue
        low = line.lower()
        if any(j in low for j in JUNK_LINE_MARKERS):
            continue
        if not any(h in low for h in JOB_TITLE_HINTS):
            continue
        # Skip generic nav items like "Careers" or "Current Openings" alone.
        if low.strip() in ("careers", "career", "current openings", "vacancies",
                            "open positions", "job openings", "apply now"):
            continue
        candidates.append(line)

    # De-dupe while preserving order.
    seen = set()
    unique = []
    for c in candidates:
        key = c.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)

    return unique[:max_snippets]


def check_lab_pages():
    items = []
    for url in LAB_CAREER_PAGES:
        try:
            raw_html = fetch_lab_page(url)
        except Exception as e:
            print(f"[warn] lab page failed: {url} ({e})")
            continue

        html_lower = raw_html.lower()
        if any(neg in html_lower for neg in LAB_PAGE_NEGATIVE):
            continue
        if not any(pos in html_lower for pos in LAB_PAGE_POSITIVE):
            continue

        name = display_name_for(url)
        now_str = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        snippets = extract_job_snippets(raw_html)

        if snippets:
            for snippet in snippets:
                items.append(
                    {
                        "title": f"{snippet} — {name}",
                        "link": url,
                        "source": name,
                        "category": "Lab Career Pages",
                        "published": now_str,
                    }
                )
        else:
            items.append(
                {
                    "title": f"Openings currently listed — {name}",
                    "link": url,
                    "source": name,
                    "category": "Lab Career Pages",
                    "published": now_str,
                }
            )
        time.sleep(0.5)
    return items


# A result's title must contain at least one of these to be treated as an
# actual job posting. Broadened from the first pass — real postings often
# use words like "posts," "positions," or "notification" instead of the
# word "vacancy" itself.
INCLUDE_KEYWORDS = [
    "vacancy", "vacancies", "recruitment", "hiring", "walk-in", "walk in",
    "job opening", "job openings", "apply now", "recruit", "post of",
    "posts of", "requires", "wanted", "career", "openings", "opening",
    "job alert", "post", "posts", "position", "positions", "notification",
    "jobs", "job", "employment", "apply", "join", "requirement",
]

# ...and must NOT contain any of these, which signal it's ordinary
# enforcement/incident news rather than a hiring notice. Trimmed down from
# the first pass — some earlier entries (like "court") were too broad and
# were blocking legitimate postings such as "High Court Recruitment."
EXCLUDE_KEYWORDS = [
    "raid", "seized", "seizure", "fine imposed", "penalty imposed",
    "penalised", "penalized", "banned", "ban on", "adulterat", "contamina",
    "poisoning", "shut down", "shuts down", "license cancel",
    "food safety index", "arrested", "fake food", "fir against",
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


def load_first_seen() -> dict:
    try:
        with open(FIRST_SEEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_first_seen(store: dict):
    with open(FIRST_SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def stable_key(item: dict) -> str:
    return hashlib.md5((item["title"].lower().strip() + "|" + item["link"]).encode()).hexdigest()


def apply_first_seen_dates(items: list, store: dict) -> list:
    """For items whose date we invented ourselves (lab career pages, where
    the site gives no real publish date), replace the timestamp with the
    date we FIRST detected that exact listing — so it only counts as "new"
    once, instead of resetting to "just now" on every scheduled run."""
    now_str = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    for it in items:
        if it["category"] != "Lab Career Pages":
            continue
        key = stable_key(it)
        if key in store:
            it["published"] = store[key]
        else:
            store[key] = now_str
            it["published"] = now_str
    return items


def prune_first_seen(store: dict, active_items: list):
    """Drop entries from the store once a listing has aged past the max
    window, so the file doesn't grow forever."""
    active_keys = {stable_key(it) for it in active_items if it["category"] == "Lab Career Pages"}
    for key in list(store.keys()):
        if key not in active_keys:
            del store[key]


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

    first_seen_store = load_first_seen()
    all_items = apply_first_seen_dates(all_items, first_seen_store)

    all_items = [it for it in all_items if is_within_age_limit(it["published"], MAX_AGE_DAYS)]
    all_items.sort(key=lambda x: to_epoch(x["published"]), reverse=True)
    all_items = all_items[:MAX_ITEMS]

    prune_first_seen(first_seen_store, all_items)
    save_first_seen(first_seen_store)

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
