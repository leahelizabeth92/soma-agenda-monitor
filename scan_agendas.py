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
import subprocess
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
LOGFILE = os.path.join(HERE, "run.log")
GIT_EXE = r"C:\Program Files\Git\cmd\git.exe"


def log(msg):
    line = f"[{datetime.datetime.now():%H:%M:%S}] {msg}"
    print(line, flush=True)
    # Also append to a file so runs launched windowless (no console) are logged.
    try:
        with open(LOGFILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


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


CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)


def parse_agenda_items(page):
    """Return one dict per agenda item with its columns split into clean fields.

    The MeetingDetail grid columns are:
      0 File#  1 Version  2 (agenda#)  3 Name  4 Type  5 Status  6 Full title ...
    'name' is the short headline; 'full' is the long legislative text. 'title'
    combines name+full and is what keyword matching runs against.
    """
    items = []
    for row in ITEM_ROW_RE.findall(page):
        cells = CELL_RE.findall(row)
        if len(cells) < 7:
            continue

        def cell(i):
            if i >= len(cells):
                return ""
            t = strip_tags(cells[i])
            # "Not available" is Legistar's placeholder for empty action/result/
            # video columns; strip it so it never leaks into a title or headline.
            t = re.sub(r"(?:\s*Not available)+\s*$", "", t).strip()
            return "" if t == "Not available" else t

        fileno = cell(0)
        if not re.fullmatch(r"\d{4,7}", fileno):
            fileno = ""
        name = cell(3)
        full = cell(6)
        if not (name or full):
            continue
        leg = LEG_RE.search(row)
        items.append({
            "file": fileno,
            "name": name,
            "type": cell(4),
            "status": cell(5),
            "full": full,
            "title": (name + " " + full).strip(),  # combined text for matching
            "url": (BASE + html.unescape(leg.group(1))) if leg else "",
        })
    return items


# ---------------------------------------------------------------------------
# Step 3: keyword matching
# ---------------------------------------------------------------------------
# Phrases that suppress an item even if it matched a trigger (populated by
# load_keyword_groups from the "exclude" list in keywords.json).
EXCLUDE_PATTERNS = []


def load_keyword_groups():
    global EXCLUDE_PATTERNS
    with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    EXCLUDE_PATTERNS = [
        re.compile(r"(?<!\w)" + re.escape(t).replace(r"\ ", r"\s+") + r"(?!\w)", re.I)
        for t in cfg.get("exclude", [])
    ]
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
    # Suppress items whose subject matter is explicitly excluded.
    for pat in EXCLUDE_PATTERNS:
        if pat.search(hay):
            return 0, []
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
def render_html(report, today, prev_files=None):
    prev_files = prev_files or set()
    total_hits = sum(len(r["hits"]) for r in report)
    flagged_meetings = [r for r in report if r["hits"]]
    other_meetings = [r for r in report if not r["hits"]]
    # An item is "new" if its file number wasn't flagged in the previous scan.
    # (Only mark when we actually have a prior scan to compare against.)
    new_count = 0
    if prev_files:
        seen = set()
        for r in flagged_meetings:
            for it in r["hits"]:
                if it["file"] and it["file"] not in prev_files and it["file"] not in seen:
                    seen.add(it["file"])
                    new_count += 1

    def esc(s):
        return html.escape(s or "")

    def highlight(text, matches, limit=None):
        if limit and len(text) > limit:
            text = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"
        out = esc(text)
        for term in sorted({t for _, t in matches}, key=len, reverse=True):
            esc_term = re.escape(term).replace(r"\ ", r"\\s+")
            out = re.sub(r"(?<!\w)(" + esc_term + r")(?!\w)",
                         r"<mark>\1</mark>", out, flags=re.I)
        return out

    def type_class(t):
        t = (t or "").lower()
        if "ordinance" in t:
            return "t-ord"
        if "resolution" in t:
            return "t-res"
        if "motion" in t:
            return "t-mot"
        if "hearing" in t:
            return "t-hear"
        return "t-other"

    cards = []
    for r in flagged_meetings:
        m = r["meeting"]
        rows = []
        for it in r["hits"]:
            cats = sorted({lbl for lbl, _ in it["matches"]})
            tags = "".join(f'<span class="tag">{esc(c)}</span>' for c in cats)
            headline = highlight(it["name"] or it["full"], it["matches"])
            desc = ""
            if it["full"] and it["full"] != it["name"]:
                desc = f'<p class="hit-desc">{highlight(it["full"], it["matches"], 260)}</p>'
            is_new = bool(prev_files) and it["file"] and it["file"] not in prev_files
            new_badge = '<span class="badge t-new">★ New</span>' if is_new else ""
            badge = new_badge + (
                f'<span class="badge {type_class(it["type"])}">{esc(it["type"])}</span>'
                if it["type"] else "")
            bits = []
            if it["file"]:
                bits.append(f'<span class="file">File&nbsp;{esc(it["file"])}</span>')
            if it["status"]:
                bits.append(f'<span>{esc(it["status"])}</span>')
            if it["url"]:
                bits.append(f'<a href="{esc(it["url"])}" target="_blank" '
                            f'rel="noopener">details&nbsp;&rarr;</a>')
            meta = ' <span class="dot">&middot;</span> '.join(bits)
            rows.append(f'''<li class="hit{" is-new" if is_new else ""}">
              <div class="hit-tags">{badge}{tags}</div>
              <h3 class="hit-title">{headline}</h3>
              {desc}
              <div class="hit-meta">{meta}</div>
            </li>''')
        agenda_link = (f'<a href="{esc(m["agenda_url"])}" target="_blank" '
                       f'rel="noopener">agenda&nbsp;PDF</a>') if m["agenda_url"] else ""
        n = len(r["hits"])
        cards.append(f'''<section class="card">
          <div class="card-head">
            <div>
              <h2>{esc(m["body"])}</h2>
              <div class="meta">{nice_date(m["date"])}{(" &middot; " + esc(m["time"])) if m["time"] else ""}
                &middot; <a href="{esc(m["detail_url"])}" target="_blank" rel="noopener">meeting&nbsp;page</a>
                {(" &middot; " + agenda_link) if agenda_link else ""}</div>
            </div>
            <span class="count">{n} item{"s" if n != 1 else ""}</span>
          </div>
          <ul class="hits">{"".join(rows)}</ul>
        </section>''')

    other_rows = []
    for r in other_meetings:
        m = r["meeting"]
        if r.get("agenda_posted"):
            note = f'no matching items &middot; {r.get("item_count", 0)} on agenda'
        else:
            note = "agenda not posted yet"
        other_rows.append(
            f'<li><a href="{esc(m["detail_url"])}" target="_blank" rel="noopener">'
            f'{esc(m["body"])}</a> <span class="muted">&mdash; {short_date(m["date"])} '
            f'&middot; {note}</span></li>')

    cards_html = "".join(cards) if cards else (
        '<section class="card"><p class="muted">No relevant agenda items found in the '
        'upcoming meetings whose agendas are posted. Agendas are usually posted a few '
        'days before each meeting &mdash; check back after the next scan.</p></section>')

    if new_count:
        s = "s" if new_count != 1 else ""
        new_banner = (f'<div class="newbanner">★ {new_count} new item{s} '
                      f'since the last scan &mdash; highlighted below.</div>')
    else:
        new_banner = ""

    now = datetime.datetime.now()
    return PAGE_TEMPLATE.format(
        generated=nice_date(today),
        generated_dt=f"{nice_date(now.date())} at {now:%I:%M %p}".replace(" 0", " "),
        new_banner=new_banner,
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
<title>SOMA West &middot; SF Agenda Monitor</title>
<style>
  :root {{
    --ink:#16161d; --soft:#55566b; --muted:#85869a; --line:#ececf3;
    --bg:#f4f4f8; --card:#ffffff; --accent:#4c5fd5; --accent-dark:#3a2e8f;
    --mark:#ffe98a; --chip:#eef0fe; --chip-ink:#3f4bc4;
  }}
  * {{ box-sizing:border-box; }}
  html {{ scroll-behavior:smooth; }}
  body {{ margin:0; color:var(--ink); background:var(--bg); line-height:1.55;
    font-family:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    -webkit-font-smoothing:antialiased; }}
  a {{ color:var(--accent); }}
  .wrap {{ max-width:860px; margin:0 auto; padding:0 22px; }}

  header.top {{ background:linear-gradient(135deg,#4c5fd5 0%,#6b3fc4 60%,#7c3aab 100%);
    color:#fff; padding:40px 22px 30px; }}
  header.top .wrap {{ padding:0; }}
  .brand {{ font-size:.75rem; letter-spacing:.14em; text-transform:uppercase;
    opacity:.85; font-weight:600; margin-bottom:8px; }}
  header.top h1 {{ margin:0 0 10px; font-size:1.75rem; line-height:1.2; font-weight:700; }}
  header.top .lede {{ margin:0; opacity:.92; font-size:1rem; max-width:60ch; }}
  .updated {{ margin-top:16px; font-size:.82rem; opacity:.85;
    display:inline-flex; align-items:center; gap:7px; }}
  .updated .dotlive {{ width:8px; height:8px; border-radius:50%; background:#7ef0b0;
    box-shadow:0 0 0 3px rgba(126,240,176,.25); }}

  .summary {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin:-22px auto 26px; }}
  .stat {{ background:var(--card); border:1px solid var(--line); border-radius:16px;
    padding:18px; box-shadow:0 6px 20px rgba(30,30,60,.06); text-align:center; }}
  .stat .n {{ font-size:2rem; font-weight:700; color:var(--accent); line-height:1; }}
  .stat .l {{ font-size:.72rem; color:var(--muted); text-transform:uppercase;
    letter-spacing:.06em; margin-top:7px; font-weight:600; }}

  h2.section {{ font-size:.8rem; letter-spacing:.08em; text-transform:uppercase;
    color:var(--muted); margin:30px 0 4px; font-weight:700; }}
  .newbanner {{ background:#fff4f4; border:1px solid #ffd5d5; color:#b33049;
    border-radius:14px; padding:12px 18px; font-size:.9rem; font-weight:600;
    margin:6px auto 0; }}

  .card {{ background:var(--card); border:1px solid var(--line); border-radius:18px;
    padding:6px 24px 22px; margin:16px auto; box-shadow:0 4px 18px rgba(30,30,60,.05);
    overflow:hidden; }}
  .card-head {{ display:flex; justify-content:space-between; align-items:flex-start;
    gap:14px; padding:18px 0 4px; border-bottom:1px solid var(--line);
    margin:0 -24px 6px; padding-left:24px; padding-right:24px; }}
  .card-head h2 {{ margin:0 0 3px; font-size:1.2rem; font-weight:700; }}
  .meta {{ font-size:.84rem; color:var(--soft); }}
  .meta a {{ text-decoration:none; }}
  .meta a:hover {{ text-decoration:underline; }}
  .count {{ flex:none; font-size:.74rem; font-weight:700; color:#fff;
    background:var(--accent); padding:5px 12px; border-radius:30px; white-space:nowrap; }}

  ul.hits {{ list-style:none; margin:0; padding:0; }}
  li.hit {{ padding:16px 0; border-bottom:1px solid var(--line); }}
  li.hit:last-child {{ border-bottom:none; padding-bottom:2px; }}
  .hit-tags {{ display:flex; flex-wrap:wrap; gap:6px; margin-bottom:8px; align-items:center; }}
  .badge {{ font-size:.66rem; font-weight:700; text-transform:uppercase; letter-spacing:.05em;
    padding:3px 9px; border-radius:6px; }}
  .t-ord {{ background:#e7ecff; color:#33409e; }}
  .t-res {{ background:#e3f6ec; color:#1f7a4d; }}
  .t-mot {{ background:#f3e9ff; color:#6b3fae; }}
  .t-hear {{ background:#fff0e0; color:#b9651b; }}
  .t-other {{ background:#eef0f3; color:#5a6072; }}
  .t-new {{ background:#ffe2e2; color:#c0344b; }}
  li.hit.is-new {{ background:linear-gradient(90deg,rgba(255,226,226,.5),transparent 60%);
    margin:0 -24px; padding-left:24px; padding-right:24px; border-radius:10px; }}
  .tag {{ font-size:.7rem; background:var(--chip); color:var(--chip-ink);
    border-radius:30px; padding:3px 10px; font-weight:600; }}
  .hit-title {{ font-size:1.02rem; font-weight:650; margin:0 0 5px; line-height:1.4; }}
  .hit-desc {{ font-size:.9rem; color:var(--soft); margin:0 0 9px; }}
  .hit-meta {{ font-size:.8rem; color:var(--muted); display:flex; flex-wrap:wrap;
    gap:8px; align-items:center; }}
  .hit-meta .file {{ font-weight:700; color:var(--soft); }}
  .hit-meta a {{ text-decoration:none; font-weight:600; }}
  .hit-meta a:hover {{ text-decoration:underline; }}
  .hit-meta .dot {{ color:var(--line); }}
  mark {{ background:var(--mark); padding:0 3px; border-radius:3px; font-weight:inherit; }}

  .muted {{ color:var(--muted); }}
  .other {{ background:var(--card); border:1px solid var(--line); border-radius:18px;
    padding:20px 24px; margin:16px auto 0; box-shadow:0 4px 18px rgba(30,30,60,.05); }}
  .other ul {{ margin:0; padding:0; list-style:none; }}
  .other li {{ font-size:.88rem; margin:9px 0; padding-left:16px; position:relative; }}
  .other li::before {{ content:"›"; position:absolute; left:0; color:var(--muted); }}
  .other a {{ text-decoration:none; font-weight:600; }}

  footer {{ max-width:860px; margin:30px auto 56px; padding:18px 22px 0;
    font-size:.8rem; color:var(--muted); border-top:1px solid var(--line); }}
  footer a {{ color:var(--accent); }}

  @media (max-width:560px) {{
    header.top {{ padding:30px 18px 26px; }}
    header.top h1 {{ font-size:1.45rem; }}
    .summary {{ grid-template-columns:1fr 1fr 1fr; gap:8px; }}
    .stat {{ padding:12px 6px; }}
    .stat .n {{ font-size:1.5rem; }}
    .stat .l {{ font-size:.6rem; }}
    .card {{ padding:6px 16px 16px; }}
    .card-head {{ flex-direction:column; margin:0 -16px 6px; padding-left:16px; padding-right:16px; }}
  }}
</style>
</head>
<body>
<header class="top"><div class="wrap">
  <div class="brand">SOMA West Neighborhood Association</div>
  <h1>SF Board &amp; Committee Agenda Monitor</h1>
  <p class="lede">Upcoming San Francisco Board of Supervisors and committee agenda items
    relevant to SOMA West &mdash; homelessness, public safety, nonprofit contracts under
    HSH&nbsp;/&nbsp;DPH&nbsp;/&nbsp;MOHCD, and the RESET center.</p>
  <div class="updated"><span class="dotlive"></span> Updated {generated_dt}</div>
</div></header>
<div class="wrap">
  <div class="summary">
    <div class="stat"><div class="n">{total_hits}</div><div class="l">Relevant items</div></div>
    <div class="stat"><div class="n">{flagged_count}</div><div class="l">Meetings flagged</div></div>
    <div class="stat"><div class="n">{meeting_count}</div><div class="l">Meetings scanned</div></div>
  </div>
  {new_banner}
  <h2 class="section">Flagged meetings</h2>
  {cards}
  <div class="other">
    <h2 class="section" style="margin-top:0">Other upcoming meetings</h2>
    <ul>{other_list}</ul>
  </div>
</div>
<footer>
  <p>Automatically generated from the
  <a href="https://sfgov.legistar.com/Calendar.aspx" target="_blank" rel="noopener">SF Legistar calendar</a>,
  twice a week. Items are flagged by keyword and may include occasional false positives &mdash;
  always confirm against the official agenda before acting. This is a volunteer neighborhood
  tool, not an official City of San Francisco source.</p>
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

    # Load history first so we can mark items that are new since the last scan.
    history_path = os.path.join(DATA, "history.json")
    history = []
    if os.path.exists(history_path):
        try:
            with open(history_path, encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []
    today_str = f"{today:%Y-%m-%d}"
    prev_files = set()
    for entry in reversed(history):
        if entry.get("date") != today_str:  # most recent scan from an earlier day
            prev_files = {it["file"] for m in entry.get("flagged", [])
                          for it in m["items"] if it.get("file")}
            break

    page = render_html(report, today, prev_files)

    index_path = os.path.join(SITE, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(page)
    archive_path = os.path.join(ARCHIVE, f"digest_{today:%Y-%m-%d}.html")
    with open(archive_path, "w", encoding="utf-8") as f:
        f.write(page)

    # Append a compact JSON record for history.
    history.append({
        "date": f"{today:%Y-%m-%d}",
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "meetings_scanned": len(report),
        "relevant_items": sum(len(r["hits"]) for r in report),
        "flagged": [
            {"body": r["meeting"]["body"],
             "date": f'{r["meeting"]["date"]:%Y-%m-%d}',
             "items": [{"file": h["file"], "title": (h["name"] or h["full"])[:160],
                        "url": h["url"]} for h in r["hits"]]}
            for r in report if r["hits"]
        ],
    })
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

    total = sum(len(r["hits"]) for r in report)
    log(f"Done. {total} relevant item(s) across {len(report)} meetings.")
    log(f"Wrote {index_path}")

    publish_to_git()
    return 0


def publish_to_git():
    """Commit the refreshed site and push it to GitHub, if a remote is set up.

    Done in-process (rather than in run.bat) so the scan + publish run as a
    single windowless pythonw process the scheduler can't console-kill.
    """
    git = GIT_EXE if os.path.exists(GIT_EXE) else "git"

    def run(args):
        return subprocess.run([git] + args, cwd=HERE,
                              capture_output=True, text=True)

    try:
        if run(["remote", "get-url", "origin"]).returncode != 0:
            log("No GitHub remote configured; site saved locally only.")
            return
        run(["add", "-A"])
        run(["commit", "-m", f"Agenda scan {datetime.date.today():%Y-%m-%d}"])
        push = run(["push"])
        if push.returncode == 0:
            log("Published updated site to GitHub.")
        else:
            log(f"git push failed: {(push.stderr or push.stdout).strip()[:200]}")
    except FileNotFoundError:
        log("git not found; could not publish (site saved locally).")
    except Exception as e:
        log(f"publish error: {e}")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log(f"ERROR: {e}")
        sys.exit(1)
