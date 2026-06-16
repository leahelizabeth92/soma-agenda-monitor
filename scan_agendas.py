#!/usr/bin/env python3
"""
SF Board of Supervisors agenda scanner for SOMA West Neighborhood Association.

What it does, in plain English:
  1. Reads the SF Legistar public calendar (sfgov.legistar.com) to find every
     upcoming Board of Supervisors and committee meeting.
  2. For each upcoming meeting that has an agenda posted, it reads the agenda
     and pulls out every agenda item.
  3. It flags items that match the keywords in keywords.json (SOMA West,
     homelessness, public safety, HSH/DPH/MOHCD contracts, the RESET center, etc.).
  4. It writes a clean web page (site/index.html) listing the flagged items,
     grouped by meeting, with links straight to the agenda and the legislation.
     A dated copy is saved in site/archive/ and a running log in site/data/.

It uses only the Python standard library, so there is nothing to install.

Run it by double-clicking run.bat, or:  python scan_agendas.py
"""

import json
import os
import re
import sys
import html
import datetime
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE = "https://sfgov.legistar.com/"
CALENDAR_URL = BASE + "Calendar.aspx"
HORIZON_DAYS = 28          # how far ahead to look
TIMEOUT = 45               # seconds per web request
HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "docs")   # 'docs' so GitHub Pages can serve it directly
ARCHIVE = os.path.join(SITE, "archive")
DATA = os.path.join(SITE, "data")
KEYWORDS_FILE = os.path.join(HERE, "keywords.json")

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "SOMAWestAgendaMonitor/1.0 (neighborhood association civic tool)")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def log(msg):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


def http_get(url, retries=3):
    """Fetch a URL and return the page text. Retries a few times on failure."""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                raw = resp.read()
                charset = resp.headers.get_content_charset()
            # Legistar pages are mostly UTF-8 but sprinkle in Windows-1252 smart
            # quotes/dashes. Honor the declared charset, then fall back cleanly.
            for enc in [charset, "utf-8", "cp1252"]:
                if not enc:
                    continue
                try:
                    return raw.decode(enc)
                except (UnicodeDecodeError, LookupError):
                    continue
            return raw.decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = e
            log(f"  fetch attempt {attempt} failed ({e}); retrying...")
    raise RuntimeError(f"Could not fetch {url}: {last_err}")


def strip_tags(fragment):
    """Turn an HTML fragment into clean readable text."""
    text = re.sub(r"<[^>]+>", " ", fragment)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def nice_date(d):
    """e.g. 'Thursday, June 18, 2026' (cross-platform, no %-d)."""
    return f"{d:%A, %B} {d.day}, {d.year}"


def short_date(d):
    """e.g. 'Thu Jun 18' (cross-platform)."""
    return f"{d:%a %b} {d.day}"


# ---------------------------------------------------------------------------
# Step 1: read the calendar -> list of upcoming meetings
# ---------------------------------------------------------------------------
# Regexes are written to tolerate Legistar's two markup variants: some skins
# wrap cell text in <font> tags, others use inline styles. So <font> is optional.
ROW_RE = re.compile(r'<tr class="rg(?:Row|AltRow)".*?</tr>', re.S)
BODY_RE = re.compile(r'hypBody"[^>]*>(?:<font[^>]*>)?\s*([^<]+?)\s*<')
DATE_RE = re.compile(r'rgSorted"[^>]*>(?:<[^>]+>)*\s*(\d{1,2}/\d{1,2}/\d{4})')
MD_RE = re.compile(r'(MeetingDetail\.aspx\?ID=\d+[^"]*)"')
AGENDA_RE = re.compile(r'hypAgenda" href="(View\.ashx\?M=A[^"]+)"')
TIME_RE = re.compile(r'lblTime"[^>]*>(?:<font[^>]*>)?\s*([^<]+?)\s*<')


def parse_calendar(page):
    """Return a list of meeting dicts found on a calendar page."""
    meetings = []
    for row in ROW_RE.findall(page):
        body = BODY_RE.search(row)
        date = DATE_RE.search(row)
        md = MD_RE.search(row)
        if not (body and date and md):
            continue
        agenda = AGENDA_RE.search(row)
        time_m = TIME_RE.search(row)
        try:
            mdate = datetime.datetime.strptime(date.group(1).strip(), "%m/%d/%Y").date()
        except ValueError:
            continue
        meetings.append({
            "body": html.unescape(body.group(1)).strip(),
            "date": mdate,
            "time": strip_tags(time_m.group(1)) if time_m else "",
            "detail_url": BASE + html.unescape(md.group(1)),
            "agenda_url": (BASE + html.unescape(agenda.group(1))) if agenda else "",
        })
    return meetings


def get_upcoming_meetings(today):
    """Current month is the default view; also pull next month for coverage."""
    page = http_get(CALENDAR_URL)
    meetings = parse_calendar(page)
    log(f"  current view: {len(meetings)} meetings parsed")

    # Pull next month too, so meetings near a month boundary are not missed.
    try:
        nm = fetch_next_month(page)
        if nm:
            extra = parse_calendar(nm)
            log(f"  next month view: {len(extra)} meetings parsed")
            seen = {m["detail_url"] for m in meetings}
            meetings += [m for m in extra if m["detail_url"] not in seen]
    except Exception as e:  # next-month is best-effort; current month still works
        log(f"  (next-month fetch skipped: {e})")

    horizon = today + datetime.timedelta(days=HORIZON_DAYS)
    upcoming = [m for m in meetings if today <= m["date"] <= horizon]
    upcoming.sort(key=lambda m: (m["date"], m["body"]))
    return upcoming


def _hidden(name, page):
    m = re.search(r'id="' + re.escape(name) + r'" value="(.*?)"', page, re.S)
    return html.unescape(m.group(1)) if m else ""


def fetch_next_month(page):
    """Drive the ASP.NET 'Next Month' postback on the calendar (best effort)."""
    import urllib.parse
    fields = {
        "__EVENTTARGET": "ctl00$ContentPlaceHolder1$lstYears",
        "__EVENTARGUMENT": "",
        "__VIEWSTATE": _hidden("__VIEWSTATE", page),
        "__VIEWSTATEGENERATOR": _hidden("__VIEWSTATEGENERATOR", page),
        "__EVENTVALIDATION": _hidden("__EVENTVALIDATION", page),
        "ctl00$ContentPlaceHolder1$lstYears": "Next Month",
        "ctl00_ContentPlaceHolder1_lstYears_ClientState":
            '{"logEntries":[],"value":"Next Month","text":"Next Month",'
            '"enabled":true,"checkedIndices":[],"checkedItemsTextOverflows":false}',
    }
    if not fields["__VIEWSTATE"]:
        return None
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        CALENDAR_URL, data=data,
        headers={"User-Agent": USER_AGENT,
                 "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read().decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Step 2: read a meeting's agenda -> list of agenda items
# ---------------------------------------------------------------------------
ITEM_ROW_RE = re.compile(r'<tr class="rg(?:Row|AltRow)".*?</tr>', re.S)
LEG_RE = re.compile(r'(LegislationDetail\.aspx\?ID=\d+[^"]*)"')
FILE_RE = re.compile(r'>\s*(\d{6})\s*<')  # SF file numbers look like 260450


def parse_agenda_items(page):
    """Return [{file, title, url}] for every agenda item on a MeetingDetail page."""
    items = []
    for row in ITEM_ROW_RE.findall(page):
        leg = LEG_RE.search(row)
        text = strip_tags(row)
        if not text:
            continue
        file_m = FILE_RE.search(row)
        fileno = file_m.group(1) if file_m else ""
        # The stripped row text starts with "<file> <version> ..."; drop that
        # leading bookkeeping so the displayed title reads cleanly.
        if fileno:
            text = re.sub(r"^" + re.escape(fileno) + r"\s+\d+\s+", "", text)
        items.append({
            "file": fileno,
            "title": text,
            "url": (BASE + html.unescape(leg.group(1))) if leg else "",
        })
    return items


# ---------------------------------------------------------------------------
# Step 3: keyword matching
# ---------------------------------------------------------------------------
def load_keyword_groups():
    with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    groups = []
    for g in cfg["groups"]:
        patterns = []
        for term in g["terms"]:
            # whole-word, case-insensitive; allow flexible whitespace in phrases
            esc = re.escape(term).replace(r"\ ", r"\s+")
            patterns.append((term, re.compile(r"(?<!\w)" + esc + r"(?!\w)", re.I)))
        groups.append({
            "id": g["id"], "label": g["label"],
            "weight": g.get("weight", 1),
            "trigger": g.get("trigger", True),
            "patterns": patterns,
        })
    return groups


def match_item(item, groups):
    """Return (score, matches) where matches is a list of (group_label, term).

    An item is only considered relevant (score > 0) if it matches at least one
    'trigger' group. Non-trigger groups (e.g. generic contract words) only add
    context to an item that already matched a trigger -- they never flag alone.
    """
    hay = item["title"]
    matches = []
    hit_groups = {}
    triggered = False
    for g in groups:
        for term, pat in g["patterns"]:
            if pat.search(hay):
                matches.append((g["label"], term))
                hit_groups[g["id"]] = g
                if g["trigger"]:
                    triggered = True
    if not triggered:
        return 0, []
    score = sum(g["weight"] for g in hit_groups.values())
    return score, matches


# ---------------------------------------------------------------------------
# Step 4: build the report data
# ---------------------------------------------------------------------------
def build_report(today):
    groups = load_keyword_groups()
    meetings = get_upcoming_meetings(today)
    log(f"Found {len(meetings)} upcoming meetings within {HORIZON_DAYS} days.")

    report = []
    for m in meetings:
        if not m["agenda_url"]:
            # No agenda posted yet -> note the meeting so it's on the radar.
            report.append({"meeting": m, "agenda_posted": False, "hits": []})
            continue
        log(f"  reading agenda: {m['body']} {m['date']:%m/%d}")
        try:
            page = http_get(m["detail_url"])
        except Exception as e:
            log(f"    could not read agenda ({e})")
            report.append({"meeting": m, "agenda_posted": True, "hits": [],
                           "error": str(e)})
            continue
        items = parse_agenda_items(page)
        hits = []
        seen_files = set()
        for it in items:
            score, matches = match_item(it, groups)
            if score > 0:
                key = it["file"] or it["title"][:60]
                if key in seen_files:
                    continue
                seen_files.add(key)
                it["score"] = score
                it["matches"] = matches
                hits.append(it)
        hits.sort(key=lambda x: -x["score"])
        report.append({"meeting": m, "agenda_posted": True, "hits": hits,
                       "item_count": len(items)})
    return report


# ---------------------------------------------------------------------------
# Step 5: render the web page
# ---------------------------------------------------------------------------
def render_html(report, today):
    total_hits = sum(len(r["hits"]) for r in report)
    flagged_meetings = [r for r in report if r["hits"]]
    other_meetings = [r for r in report if not r["hits"]]

    def esc(s):
        return html.escape(s or "")

    def highlight(text, matches):
        out = esc(text)
        for _, term in sorted({m for m in matches}, key=lambda t: -len(t[1])):
            esc_term = re.escape(term).replace(r"\ ", r"\\s+")
            out = re.sub(r"(?<!\w)(" + esc_term + r")(?!\w)",
                         r"<mark>\1</mark>", out, flags=re.I)
        return out

    cards = []
    for r in flagged_meetings:
        m = r["meeting"]
        rows = []
        for it in r["hits"]:
            cats = sorted({lbl for lbl, _ in it["matches"]})
            tags = "".join(f'<span class="tag">{esc(c)}</span>' for c in cats)
            title = highlight(it["title"], it["matches"])
            fileno = f'<span class="file">File {esc(it["file"])}</span>' if it["file"] else ""
            link = (f'<a href="{esc(it["url"])}" target="_blank" rel="noopener">'
                    f'open&nbsp;item&nbsp;&raquo;</a>') if it["url"] else ""
            rows.append(f'''<li class="hit">
              <div class="hit-head">{fileno} {tags}</div>
              <div class="hit-title">{title}</div>
              <div class="hit-link">{link}</div>
            </li>''')
        agenda_link = (f'<a href="{esc(m["agenda_url"])}" target="_blank" '
                       f'rel="noopener">full agenda (PDF)</a>') if m["agenda_url"] else ""
        cards.append(f'''<section class="card">
          <div class="card-head">
            <h2>{esc(m["body"])}</h2>
            <div class="meta">{nice_date(m["date"])} &middot; {esc(m["time"])}
              &middot; <a href="{esc(m["detail_url"])}" target="_blank" rel="noopener">meeting page</a>
              {(" &middot; " + agenda_link) if agenda_link else ""}</div>
          </div>
          <div class="count">{len(r["hits"])} relevant item(s)</div>
          <ul class="hits">{"".join(rows)}</ul>
        </section>''')

    other_rows = []
    for r in other_meetings:
        m = r["meeting"]
        if r.get("agenda_posted"):
            note = f'no matching items ({r.get("item_count", 0)} on agenda)'
        else:
            note = "agenda not posted yet"
        other_rows.append(
            f'<li><strong>{esc(m["body"])}</strong> &mdash; '
            f'{short_date(m["date"])} &middot; '
            f'<a href="{esc(m["detail_url"])}" target="_blank" rel="noopener">meeting page</a> '
            f'<span class="muted">({note})</span></li>')

    cards_html = "".join(cards) if cards else (
        '<section class="card"><p class="muted">No relevant agenda items found '
        'in the upcoming meetings whose agendas are posted. Check back after the '
        'next scan &mdash; agendas are usually posted a few days before each meeting.</p></section>')

    return PAGE_TEMPLATE.format(
        generated=nice_date(today),
        generated_dt=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        total_hits=total_hits,
        flagged_count=len(flagged_meetings),
        meeting_count=len(report),
        cards=cards_html,
        other_list="".join(other_rows) or "<li class='muted'>None.</li>",
    )


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SOMA West &middot; SF Board &amp; Committee Agenda Monitor</title>
<style>
  :root {{ --ink:#1a1a2e; --muted:#6b7280; --line:#e5e7eb; --bg:#f7f7fb;
           --accent:#3b5bdb; --mark:#fff3bf; --card:#ffffff; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
          color:var(--ink); background:var(--bg); line-height:1.5; }}
  header.top {{ background:linear-gradient(135deg,#3b5bdb,#5f3dc4); color:#fff;
                padding:28px 20px; }}
  header.top .wrap {{ max-width:920px; margin:0 auto; }}
  header.top h1 {{ margin:0 0 4px; font-size:1.5rem; }}
  header.top p {{ margin:0; opacity:.9; font-size:.95rem; }}
  .wrap {{ max-width:920px; margin:0 auto; padding:0 20px; }}
  .summary {{ display:flex; gap:18px; flex-wrap:wrap; margin:20px auto; }}
  .stat {{ background:var(--card); border:1px solid var(--line); border-radius:12px;
           padding:14px 18px; flex:1; min-width:140px; }}
  .stat .n {{ font-size:1.8rem; font-weight:700; color:var(--accent); }}
  .stat .l {{ font-size:.8rem; color:var(--muted); text-transform:uppercase;
              letter-spacing:.04em; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:14px;
           padding:20px; margin:16px auto; box-shadow:0 1px 3px rgba(0,0,0,.04); }}
  .card-head h2 {{ margin:0 0 4px; font-size:1.15rem; }}
  .meta {{ font-size:.85rem; color:var(--muted); }}
  .meta a {{ color:var(--accent); text-decoration:none; }}
  .count {{ display:inline-block; margin:10px 0; font-size:.78rem; font-weight:600;
            color:#fff; background:var(--accent); padding:2px 10px; border-radius:20px; }}
  ul.hits {{ list-style:none; margin:0; padding:0; }}
  li.hit {{ border-top:1px solid var(--line); padding:12px 0; }}
  .hit-head {{ margin-bottom:4px; }}
  .file {{ font-size:.75rem; color:var(--muted); font-weight:600; margin-right:8px; }}
  .tag {{ display:inline-block; font-size:.7rem; background:#eef2ff; color:#3b5bdb;
          border-radius:6px; padding:1px 7px; margin:0 4px 4px 0; }}
  .hit-title {{ font-size:.95rem; }}
  .hit-link a {{ font-size:.82rem; color:var(--accent); text-decoration:none; }}
  mark {{ background:var(--mark); padding:0 2px; border-radius:3px; }}
  .muted {{ color:var(--muted); }}
  .other {{ background:var(--card); border:1px solid var(--line); border-radius:14px;
            padding:20px; margin:16px auto; }}
  .other h3 {{ margin:0 0 10px; font-size:1rem; }}
  .other ul {{ margin:0; padding-left:18px; }}
  .other li {{ font-size:.88rem; margin:5px 0; }}
  footer {{ max-width:920px; margin:24px auto 50px; padding:0 20px;
            font-size:.8rem; color:var(--muted); }}
  footer a {{ color:var(--accent); }}
</style>
</head>
<body>
<header class="top"><div class="wrap">
  <h1>SF Board &amp; Committee Agenda Monitor</h1>
  <p>SOMA West Neighborhood Association &middot; updated {generated}</p>
</div></header>
<div class="wrap">
  <div class="summary">
    <div class="stat"><div class="n">{total_hits}</div><div class="l">relevant items</div></div>
    <div class="stat"><div class="n">{flagged_count}</div><div class="l">meetings flagged</div></div>
    <div class="stat"><div class="n">{meeting_count}</div><div class="l">upcoming meetings scanned</div></div>
  </div>
  {cards}
  <div class="other">
    <h3>Other upcoming meetings (no flagged items)</h3>
    <ul>{other_list}</ul>
  </div>
</div>
<footer>
  <p>Automatically generated from the
  <a href="https://sfgov.legistar.com/Calendar.aspx" target="_blank" rel="noopener">SF Legistar calendar</a>
  on {generated_dt}. Items are flagged by keyword (see keywords list) and may include
  false positives &mdash; always confirm against the official agenda. This is a volunteer
  neighborhood tool, not an official City source.</p>
</footer>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    os.makedirs(ARCHIVE, exist_ok=True)
    os.makedirs(DATA, exist_ok=True)
    today = datetime.date.today()
    log(f"Scan starting for {today:%Y-%m-%d}")

    report = build_report(today)
    page = render_html(report, today)

    index_path = os.path.join(SITE, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(page)
    archive_path = os.path.join(ARCHIVE, f"digest_{today:%Y-%m-%d}.html")
    with open(archive_path, "w", encoding="utf-8") as f:
        f.write(page)

    # Append a compact JSON record for history.
    history_path = os.path.join(DATA, "history.json")
    history = []
    if os.path.exists(history_path):
        try:
            with open(history_path, encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []
    history.append({
        "date": f"{today:%Y-%m-%d}",
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "meetings_scanned": len(report),
        "relevant_items": sum(len(r["hits"]) for r in report),
        "flagged": [
            {"body": r["meeting"]["body"],
             "date": f'{r["meeting"]["date"]:%Y-%m-%d}',
             "items": [{"file": h["file"], "title": h["title"][:160],
                        "url": h["url"]} for h in r["hits"]]}
            for r in report if r["hits"]
        ],
    })
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

    total = sum(len(r["hits"]) for r in report)
    log(f"Done. {total} relevant item(s) across {len(report)} meetings.")
    log(f"Wrote {index_path}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log(f"ERROR: {e}")
        sys.exit(1)
