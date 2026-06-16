# Publishing the site to a shareable web link (one-time setup)

The tool already builds the website into the `docs/` folder on your computer.
To put it online at a link you can send to other committee members, we'll use
**GitHub Pages** — a free, permanent host. After this one-time setup, every
scan (twice a week) automatically updates the live site.

You only do this once. It takes about 10 minutes.

---

## Step 1 — Create a free GitHub account (skip if you have one)

Go to <https://github.com/signup> and create an account. A free account is all
you need.

## Step 2 — Create an empty repository

1. Go to <https://github.com/new>
2. **Repository name:** `soma-agenda-monitor`
3. Choose **Public** (required for free GitHub Pages).
4. Do **not** check "Add a README" / "Add .gitignore" — leave it empty.
5. Click **Create repository**.
6. Copy the URL shown, e.g. `https://github.com/YOURNAME/soma-agenda-monitor.git`

## Step 3 — Connect this folder to that repository

Tell Claude: *"connect the agenda monitor to my GitHub repo: <paste the URL>"*
— and it will run the connection commands for you. (Or run them yourself:)

```
cd C:\Users\leahe\soma-agenda-monitor
git branch -M main
git remote add origin https://github.com/YOURNAME/soma-agenda-monitor.git
git push -u origin main
```

The first push will pop up a GitHub sign-in window — sign in once. After that,
the twice-weekly scans push updates automatically with no prompts.

## Step 4 — Turn on GitHub Pages

1. On your repository page, click **Settings** → **Pages** (left sidebar).
2. Under **Build and deployment → Source**, choose **Deploy from a branch**.
3. Set **Branch** to `main` and the folder to **`/docs`**, then **Save**.
4. Wait ~1 minute. The page will show your live link:
   **`https://YOURNAME.github.io/soma-agenda-monitor/`**

That link is what you share. It refreshes automatically every Monday and
Thursday after the scan runs.

---

## Troubleshooting

- **Site shows a 404 for a minute** — GitHub Pages takes a moment to build the
  first time. Refresh after a minute.
- **Pushes stop working later** — open a terminal in this folder and run
  `git push` once manually to re-authenticate.
- **You don't want a public site** — keep using the local `docs/index.html`
  file (open it in a browser) and email it to others, or ask Claude about a
  private hosting option.
