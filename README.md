# Expense Tracker

A personal finance app: import your bank statements (CSV), categorize your spending, and keep track of your net worth. It runs on your own computer and stores everything in a PostgreSQL database.

**What it does**

- **Imports bank files** (UBS and CGD out of the box; add other banks on the *Banks* page) and lets you check every row before it's added.
- **Categorizes transactions** automatically with your own keyword rules, and with OpenAI for anything the rules don't catch.
- **Splits shared expenses** and counts refunds and repayments against the category they belong to.
- **Dashboards** for each year and month, in CHF or EUR (other currencies are converted with daily ECB rates).
- **Net worth**: your accounts, their values over time, and how your money is allocated.

---

## Contents

1. [First-time setup](#1-first-time-setup)
2. [Everyday use](#2-everyday-use)
3. [Using the app, page by page](#3-using-the-app-page-by-page)
4. [Settings reference (`.env`)](#4-settings-reference-env)
5. [Password reset emails](#5-password-reset-emails)
6. [For development](#6-for-development)
7. [Hosting it online (optional)](#7-hosting-it-online-optional)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. First-time setup

You need **Python 3.13+**, **PostgreSQL 14+** and **Git**. The commands below are for Windows PowerShell, run from the project folder.

**1. Get the code and create a virtual environment**

```powershell
git clone https://github.com/Saphira7544/ExpenseTracker.git
cd ExpenseTracker
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**2. Create a database** called `expense_tracker` in PostgreSQL (in pgAdmin: right-click *Databases* > *Create*).

**3. Create a file called `.env`** in the project folder:

```dotenv
DB_HOST=localhost
DB_PORT=5432
DB_NAME=expense_tracker
DB_USER=postgres
DB_PASSWORD=your-postgres-password

# Required: a long random string. Create one with:
#   .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
APP_SECRET_KEY=paste-it-here

# Optional: automatic categorization with OpenAI (costs a little per upload)
OPENAI_API_KEY=your-openai-key
```

`.env` holds passwords: never commit it or share it. All the other settings are in [section 4](#4-settings-reference-env).

**4. Install the app on this PC**

```powershell
.\.venv\Scripts\python.exe -m localapp install
```

This adds **Expense Tracker** to the Start menu. Open it: the app starts and your browser opens **http://expenses.localhost**. The database tables are created automatically the first time.

**5. Create your account**

Click *Register*. New accounts need approval, so make your first account an approved admin once, in PostgreSQL (pgAdmin's query tool or `psql`):

```sql
UPDATE users SET is_approved = TRUE, is_admin = TRUE WHERE email = 'you@example.com';
```

Then sign in. Other people who register can be approved by an admin without SQL: open `/docs` while signed in and use `POST /admin/users/{user_id}/approve` (`GET /admin/pending-users` lists who's waiting).

**6. Before your first upload**, see [Settings](#settings) to set up import exclusions.

---

## 2. Everyday use

- **Open it** from **Start > Expense Tracker**, or go to **http://expenses.localhost**. If the app isn't running, the Start-menu icon starts it first (no window opens, it runs in the background).
- **Start it automatically**: tick *Start Expense Tracker automatically when I sign in to Windows* in **Settings > App**. If it's off, it only starts when you open it from the Start menu.
- **Restart** (Settings > App) loads new code after the project files change. An *Update ready · Restart* button also appears in the sidebar when that happens. **Stop** shuts it down until you open it again.
- It's only reachable from this computer, not from other devices on your network.
- If something goes wrong, the details are in `logs/server.log`.
- To remove the Start-menu and startup shortcuts: `.\.venv\Scripts\python.exe -m localapp uninstall`.

> The address `expenses.localhost` needs no setup: browsers send any `*.localhost` name to your own computer. If another program is already using port 80, the app uses `http://expenses.localhost:8500` instead.

---

## 3. Using the app, page by page

### Upload Files
Drop one or more bank CSV files and click **Review upload**. Nothing is added yet: a dialog shows, per file, how many rows were found, excluded, **already imported** and **new**, and lists the new rows with their suggested category (from your rules, or the AI). Untick any row you don't want, then **Import**.

### Transactions
Search and filter everything you've imported.
- **Pencil**: edit any transaction (imported ones too). **Add transaction** adds one by hand, e.g. cash.
- **Category picker** in each row for quick changes; select several rows to change their category or **delete** them in one go.
- **Scissors**: split a transaction across categories (e.g. a shared grocery bill). Undo it with the arrow icon.
- A category you set by hand is marked *manual* and rules won't change it; the wand icon hands it back to the rules.

### Rules
Keyword rules: "description contains `migros` → Groceries". The longest matching keyword wins. *Preview* shows what re-running your rules would change before you apply it.

### Dashboard and Monthly
Yearly and monthly views of income, spending, investing and your savings rate, in CHF or EUR (switch at the top). How the numbers work:
- **Income**: the categories you mark as income in Settings (by default *Salary*).
- **Invested**: money going into investment categories (by default *Investments*). It counts as saved, not spent.
- **Expenses**: everything else, **netted per category**. Money coming back (a refund, or someone paying you back) lowers that category instead of counting as income. For a bill you share: split it so the other person's half goes to *Transfers*, and tag their repayment *Transfers* too; the two cancel out.
- **Ignored**: the *Internal* category (moving money between your own accounts, currency exchanges) isn't counted at all.
- Split transactions count as their parts. Each category always has the same color.

### Net Worth
Your accounts, grouped by bank, with their latest value. Record a new value with the trend-arrow icon (for ETFs/stocks, enter quantity and price; *Use ECB rate* fills in the exchange rate). **Record snapshot** saves today's total as a point on your net-worth trend. *Net Worth Config* holds the lists you pick from (banks, asset categories, currencies…), and *Net Worth Analytics* shows the trend and how your money is allocated.

### Settings
- **Import exclusions**: text that marks rows to skip when importing, per bank, e.g. transfers between your own accounts or card top-ups (`Payment to card`).
- **How categories count**: which categories are income, investments, or ignored.
- **Display currency**, and **App** (start at sign-in, restart, stop).

### Banks
How each bank's CSV file is read. To add a bank, click **Add bank format** and pick a sample export under *Test with a sample file*: the file's columns are suggested in each field and you see the parsed transactions before saving.

---

## 4. Settings reference (`.env`)

Edit `.env` in the project folder, then restart the app (Settings > App > Restart).

| Setting | Needed? | What it's for |
|---|---|---|
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Yes (or `DATABASE_URL`) | Your PostgreSQL database. |
| `DATABASE_URL` | Instead of the above | One connection string, e.g. from a hosting provider. |
| `APP_SECRET_KEY` | **Yes** | Protects sign-in sessions. The app won't start without it. |
| `OPENAI_API_KEY` | Optional | AI categorization of rows your rules don't match. |
| `ENABLE_LLM_CATEGORIZATION` | Optional | `false` to turn the AI off (default `true`). |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | Optional | Sending password reset emails (see below). |
| `APP_BASE_URL` | Optional | The app's address used in emailed links. Set automatically by the Start-menu app. |
| `SESSION_MAX_AGE_DAYS` | Optional | How long you stay signed in (default 14). |
| `UPLOAD_DIR` | Optional | Where uploaded files are kept (default `storage/uploads`). |

---

## 5. Password reset emails

*Forgot password?* on the sign-in page emails a link to choose a new password. The link works once, for 30 minutes, and resetting signs you out everywhere else.

To send the emails, add your mail account to `.env`. For Gmail:

```dotenv
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM=you@gmail.com
```

`SMTP_PASSWORD` is a Gmail **app password**, not your normal password: Google Account > Security > 2-Step Verification > App passwords.

**No email set up yet?** The reset link is written to `logs/server.log` instead. Open that file and copy the link from the last *Password reset link* line.

---

## 6. For development

Run with automatic reload while you edit (in parallel with the Start-menu app is fine, they use different ports):

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Then open http://localhost:8000. Every API endpoint is documented at `/docs`.

**Tests** (no database, internet or API keys needed):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

**Where things are**

```text
app/
  main.py            app entry point and page routes
  api/routes/        API endpoints (one file per area)
  services/          the actual logic: imports, analytics, net worth, exchange rates...
  templates/         HTML pages
  static/            CSS and JavaScript
  core/              settings, sign-in, categories and their colors
categorizers/        rule-based and OpenAI categorization
parsers/             reading bank CSV files (bank_configs.py = the starting bank formats)
legacy_db/           creates the database tables and runs one-time data updates at startup
localapp/            the Start-menu app: launcher, background server, shortcuts
tests/               automated tests
logs/                server log (not in git)
storage/uploads/     uploaded bank files (not in git)
```

**Database changes** happen automatically when the app starts (new tables and columns are added; existing data is kept). Back up the database before updating to a new version:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" -U postgres --format=custom --file=expense_tracker_backup.dump expense_tracker
```

(Change `18` to your PostgreSQL version. To restore: `pg_restore.exe` from the same folder, with `--dbname=expense_tracker`.)

---

## 7. Hosting it online (optional)

The app can also run on a hosting service such as Railway:

1. Push the code to GitHub and create a Railway project from it, plus a PostgreSQL service.
2. In Railway's *Variables*, reference the database's `DATABASE_URL` and add `APP_SECRET_KEY` (a new one), `OPENAI_API_KEY`, the `SMTP_*` settings and `APP_BASE_URL` (your Railway address).
3. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

To copy your local data across, back it up with `pg_dump` (above) and load it with `pg_restore.exe --no-owner --dbname="<railway DATABASE_URL>" expense_tracker_backup.dump`. Keep both backups until you've checked the copy. Hosted servers often lose uploaded files on redeploy; that's fine, everything that matters is in the database.

---

## 8. Troubleshooting

| Problem | What to do |
|---|---|
| The Start-menu app doesn't open | A message box points to `logs/server.log`; the error is at the end of that file. |
| `APP_SECRET_KEY is not set` | Add it to `.env` (see [setup step 3](#1-first-time-setup)). |
| Can't connect to the database | Check PostgreSQL is running (Windows *Services*: `postgresql-x64-…`) and the `DB_*` values in `.env`. |
| Upload says *no bank format recognises this file* | Open *Banks*, edit or add the format, and use *Test with a sample file* to see what doesn't match. |
| Rows you don't want keep getting imported | Add the text that identifies them under *Settings > Import exclusions*. |
| *No exchange rate available* on the dashboards | Exchange rates are downloaded from the ECB; check the internet connection and reload. |
| Forgot your password | *Forgot password?* on the sign-in page. Without email set up, the link is in `logs/server.log`. |
| AI categorization doesn't happen | Check `OPENAI_API_KEY` in `.env` and that `ENABLE_LLM_CATEGORIZATION` isn't `false`, then restart. |

---

**Privacy.** This app handles your bank data. Keep `.env`, uploaded files and database backups out of git (they already are, via `.gitignore`), and keep regular database backups. Transaction descriptions are sent to OpenAI only when AI categorization is on.

**License.** No license yet: all rights reserved by the author.
