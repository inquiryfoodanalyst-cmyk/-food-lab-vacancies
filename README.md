# Food Testing Lab Vacancy Feed (India) — Live & Automated

A self-updating vacancy board for food testing laboratories across India,
pulling from news, government/FSSAI notices, job portals (Naukri, Indeed,
Shine, TimesJobs), and public LinkedIn/X posts — all via Google's public
News RSS search, so no paid APIs or scraping-ToS issues.

## How it works
1. `fetch_vacancies.py` queries Google News RSS with a set of targeted
   searches and writes the results to `vacancies.json`.
2. `.github/workflows/update.yml` runs that script automatically every
   3 hours on GitHub's servers, commits the refreshed JSON, and deploys
   the whole folder to GitHub Pages.
3. `index.html` is the public page — it reads `vacancies.json` and renders
   the live feed. This is the page you embed on your site.

## One-time setup (about 10 minutes)
1. **Create a GitHub repo** (free account is fine) — e.g. `food-lab-vacancies`.
2. **Upload all files in this folder**, keeping the `.github/workflows/`
   folder structure intact.
3. In the repo, go to **Settings → Pages** → under "Build and deployment",
   set Source to **GitHub Actions**.
4. Go to the **Actions** tab → select "Update vacancy feed" → click
   **Run workflow** once, to generate the first `vacancies.json` and deploy.
5. Your live page will be at:
   `https://<your-username>.github.io/food-lab-vacancies/`
6. After that, it updates itself every 3 hours — no further action needed.

## Embedding it on your website
Add this where you want the feed to appear:

```html
<iframe
  src="https://<your-username>.github.io/food-lab-vacancies/"
  style="width:100%; height:900px; border:none;"
  loading="lazy">
</iframe>
```

Or, if you'd rather match your site's own styling, `index.html` is plain
HTML/CSS/JS — copy the `<div class="feed">` rendering logic directly into
your existing page template.

## Customizing
- **Change how often it refreshes**: edit the `cron` line in
  `.github/workflows/update.yml` (currently `0 */3 * * *` = every 3 hours).
- **Add or remove search sources**: edit the `QUERIES` list in
  `fetch_vacancies.py` — each entry is `(category label, search query)`.
- **Add more social platforms**: append more `site:` queries (e.g.
  `site:facebook.com` or a specific recruiter's page) to `QUERIES`.

## Limitations to know about
- This uses **Google-indexed public posts**, not official LinkedIn/X APIs —
  those require paid developer access and stricter usage terms. Indexed
  coverage is good but not exhaustive (posts can take time to appear, and
  very recent ones may lag by a few hours).
- Google News RSS can occasionally rate-limit if run too frequently —
  every 3 hours is a safe, reliable interval.
