# SOMA West — SF Board & Committee Agenda Monitor

A small tool that scans the San Francisco Board of Supervisors and committee
agendas and flags items relevant to SOMA West: homelessness, public safety,
nonprofit contracts under HSH / DPH / MOHCD, the RESET center, specific service
providers (TODCO, TNDC, etc.), and the neighborhood's active issues.

It produces a clean webpage (in the `docs/` folder) that can be shared with
other committee members.

---

## How it works

1. Reads the public **SF Legistar calendar** (`sfgov.legistar.com`) to find every
   upcoming Board and committee meeting in the next ~4 weeks.
2. For each meeting that has an agenda posted, it reads the agenda items.
3. It flags items matching the keywords in **`keywords.json`**.
4. It rebuilds **`docs/index.html`** — the shareable digest — plus a dated copy
   in `docs/archive/` and a running log in `docs/data/history.json`.

Nothing needs to be installed — it uses only the standard Python library.

---

## Running it

**Manually:** double-click **`run.bat`**, or in a terminal:

```
python scan_agendas.py
```

Then open `docs/index.html` in any browser.

**Automatically (twice a week):** a Windows Scheduled Task named
**"SOMA West Agenda Monitor"** runs `run.bat` every **Monday and Thursday at
7:30 AM** (your PC must be on and signed in at that time). To change the
schedule, open **Task Scheduler**, find that task, and edit its trigger.

---

## Changing what gets flagged

Open **`keywords.json`** in any text editor. Each group has:

- `label` — the tag shown on the website
- `weight` — higher numbers sort to the top
- `trigger` — `true` means this group can flag an item on its own;
  `false` means it only adds context/detail to an item already flagged by a
  trigger group (this is how generic words like "contract" avoid creating noise)
- `terms` — the words/phrases to match (whole-word, case-insensitive)

Add or delete terms and save. No coding required. The change takes effect on the
next scan.

---

## Publishing the website (so others can see it)

The site is generated into the `docs/` folder. To put it online at a shareable
link, this repo is set up to publish via **GitHub Pages**: once a GitHub remote
named `origin` is configured, `run.bat` automatically commits and pushes the
updated `docs/` folder after every scan, and GitHub serves it at a public URL.

See `SETUP-PUBLISHING.md` for the one-time setup steps.

---

## Files

| File | What it is |
|------|------------|
| `scan_agendas.py` | The scanner (the actual program) |
| `keywords.json` | The editable list of what to flag |
| `run.bat` | Runs a scan and publishes (used by the scheduled task) |
| `docs/index.html` | The shareable digest webpage |
| `docs/archive/` | Dated copies of each scan |
| `docs/data/history.json` | Machine-readable history of every scan |
| `run.log` | Log of recent runs (for troubleshooting) |

---

*This is a volunteer neighborhood tool, not an official City source. Flagged
items are keyword matches and may include false positives — always confirm
against the official agenda before acting.*
