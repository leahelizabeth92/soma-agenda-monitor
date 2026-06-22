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
**"SOMA West Agenda Monitor"** runs the scanner every **Monday and Thursday at
7:30 AM**. For reliability the task launches `pythonw.exe scan_agendas.py`
directly (a windowless Python process, so Windows can't console-kill it mid-run),
and the script publishes to GitHub itself when it finishes. The task is set to
**wake the PC from sleep** to run, and to **catch up** the next time the PC is on
if it was fully shut down. To change the schedule, open **Task Scheduler**, find
that task, and edit its trigger.

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

The site is generated into the `docs/` folder and published via **GitHub Pages**
at https://leahelizabeth92.github.io/soma-agenda-monitor/ . After every scan the
script automatically commits and pushes the updated `docs/` folder to the
`origin` remote, and GitHub serves it at that public URL.

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
