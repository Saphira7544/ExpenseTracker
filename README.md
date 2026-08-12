# ExpenseTracker

ExpenseTracker is a personal finance web application for importing bank transaction files, categorizing transactions, managing categorization rules, splitting transactions, and tracking net worth. It is built with FastAPI, PostgreSQL, SQLAlchemy, server-rendered Jinja templates, and optional OpenAI-assisted categorization.

## Features

- User registration, login, logout, signed session cookies, and password hashing with bcrypt.
- Import of supported bank transaction files through the upload interface.
- Bank-format detection and configurable parsing through the `parsers/` package.
- Rule-based transaction categorization.
- Optional OpenAI categorization for transactions that remain uncategorized.
- Transaction filtering by account, category, search term, date range, amount direction, amount range, and split status.
- Manual category changes, bulk category changes, and reverting a category to automatic categorization.
- Transaction splitting with a remainder category.
- User-specific categorization rules and rule re-run preview/apply operations.
- Net-worth accounts, lookup values, valuations, snapshots, liquidity classification, and CHF totals.
- PostgreSQL persistence for users, transactions, rules, splits, and net-worth data.

## Technology

- Python 3.13 or newer
- FastAPI and Uvicorn
- PostgreSQL
- SQLAlchemy
- Jinja2 templates
- bcrypt and itsdangerous for authentication
- pandas and parser utilities for transaction imports
- OpenAI Python SDK for optional LLM categorization
- Railway-compatible deployment using Uvicorn

## Project structure

```text
ExpenseTracker/
├── app/
│   ├── main.py                 # FastAPI application entrypoint
│   ├── api/routes/             # HTTP routes and API endpoints
│   ├── core/                   # Settings, authentication, dependencies
│   ├── db/                     # SQLAlchemy engine/session setup
│   ├── services/               # Business logic and database operations
│   ├── templates/              # Jinja HTML templates
│   └── static/                 # CSS and static assets
├── categorizers/               # Rule-based and OpenAI categorization
├── legacy_db/                  # PostgreSQL table creation and transaction inserts
├── models/                     # Shared data models
├── parsers/                    # Bank configuration detection and parsing
├── storage/                    # Runtime upload storage
├── utils/                      # Utility functions
├── requirements.txt            # Python dependencies
├── .env                        # Local secrets; do not commit
└── README.md
```

The application entrypoint is `app/main.py`, and the FastAPI object is named `app`. From the repository root, the application is started with `uvicorn app.main:app`.

## Prerequisites

Install the following before setting up the project:

1. Python 3.13 or newer.
2. PostgreSQL 14 or newer, either locally or through a hosted provider such as Railway.
3. Git.
4. A PostgreSQL client such as `psql`, DBeaver, or TablePlus if you need to inspect or migrate data.
5. An OpenAI API key if LLM categorization is enabled.

On Windows, make sure `python` and `git` are available in PowerShell. On macOS/Linux, use the corresponding shell commands shown below.

## Clone the repository

Replace the placeholder URL with the repository's actual GitHub URL:

```bash
git clone https://github.com/Saphira7544/ExpenseTracker.git
cd <your-repository>
```

If the repository is private, authenticate with GitHub before cloning or use an SSH URL:

```bash
git clone git@github.com:Saphira7544/ExpenseTracker.git
```

## Create a virtual environment

Create the environment from the repository root:

### Windows PowerShell

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation for the current user, run PowerShell as your normal user and execute:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Then activate the environment again.

### macOS/Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

When the environment is active, your terminal normally shows `(.venv)` at the beginning of the prompt.

## Install dependencies

Upgrade packaging tools and install the project dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The production dependency list must include `psycopg2-binary`, not only `psycopg2`, unless the deployment image explicitly installs PostgreSQL client libraries. `psycopg2-binary` avoids the common Railway error involving a missing `libpq.so.5` library.

After installation, verify the important packages:

```bash
python -c "import fastapi, sqlalchemy, psycopg2; print('Dependencies OK')"
```

## Configure PostgreSQL

The application uses PostgreSQL. It does not create a local SQLite database file. The table-creation functions in `legacy_db/` connect to PostgreSQL using the credentials in the environment and create the required tables at application startup.

Create a PostgreSQL database locally or provision one through a hosted provider. Then create a local `.env` file in the repository root. Do not commit this file.

Example `.env`:

```dotenv
DB_USER=postgres
DB_PASSWORD=your-local-password
DB_HOST=localhost
DB_PORT=5432
DB_NAME=expense_tracker

UPLOAD_DIR=storage/uploads
APP_SECRET_KEY=replace-with-a-long-random-secret
SESSION_COOKIE_NAME=expense_tracker_session
ENABLE_LLM_CATEGORIZATION=true
OPENAI_API_KEY=your-openai-api-key
```

Use the exact database names, host, port, username, and password for your PostgreSQL installation. For a Railway deployment, set these values in Railway Variables instead of committing them to `.env`.

### Database URL behavior

The application constructs this SQLAlchemy URL from the database variables:

```text
postgresql+psycopg2://DB_USER:DB_PASSWORD@DB_HOST:DB_PORT/DB_NAME
```

Do not put the literal text `None` in any database variable. Missing variables can produce an invalid URL and prevent the application from starting.

### Secret handling

Never commit any of the following:

- `.env` files.
- PostgreSQL passwords or full connection strings.
- OpenAI API keys.
- Session or application secret keys.
- Database dumps containing sensitive personal or financial data.

Use GitHub secret scanning and rotate a credential immediately if it has been exposed.

## Initialize the database

Start the application once after PostgreSQL and the environment variables are configured. The startup lifespan creates the following tables:

- `users`.
- `transactions`.
- `transaction_splits`.
- `category_rules`.
- `networth_institutions`.
- `networth_asset_categories`.
- `networth_account_types`.
- `networth_currencies`.
- `networth_liquidity_statuses`.
- `networth_accounts`.
- `networth_valuations`.
- `networth_snapshots`.

The startup process is implemented in `app/main.py` and calls the table-creation functions from `legacy_db/`. Table creation is idempotent because it uses `CREATE TABLE IF NOT EXISTS`.

For a clean production database, let the application create the tables rather than manually creating a second, differently named schema.

## Run locally

From the repository root with the virtual environment active:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open the displayed address in a browser:

```text
http://127.0.0.1:8000
```

The root page requires authentication. Unauthenticated visitors should be sent to `/login`. Other useful pages include:

- `/login` — sign in.
- `/register` — request an account.
- `/upload` — upload bank files.
- `/transactions` — view and manage transactions.
- `/rules` — manage categorization rules.
- `/networth` — view net worth data.
- `/networth/config` — configure net-worth lookup values and accounts.

The interactive API documentation is available at `/docs` when the app is running.

## User approval

New registrations are created as unapproved accounts. The login route refuses access until `is_approved` is true.

For local development, approve a user directly in PostgreSQL after registering:

```sql
UPDATE users
SET is_approved = TRUE
WHERE email = 'your@email.example';
```

If your database schema includes administrator fields, grant administrator access only when needed and only to a trusted account. Use a database client or a controlled administrative process; never expose database credentials in the browser.

## Configure OpenAI categorization

The upload service imports the OpenAI categorizer and can use it for transactions that remain uncategorized after rule-based categorization. Set:

```dotenv
ENABLE_LLM_CATEGORIZATION=true
OPENAI_API_KEY=your-api-key
```

To disable LLM categorization for a local test environment, set:

```dotenv
ENABLE_LLM_CATEGORIZATION=false
```

The OpenAI key should be stored only in `.env` locally and in the hosting provider's secret/environment-variable manager in production. Never place it directly in `categorizers/openAI.py` or commit it to Git.

LLM calls may incur usage costs. Set usage limits and monitor the associated OpenAI account.

## Upload and categorize transactions

1. Register an account.
2. Approve the account in PostgreSQL if approval is enabled.
3. Log in.
4. Open `/upload`.
5. Select one or more supported bank files.
6. Upload the files.
7. The application detects the bank format, parses the transactions, attaches them to the current user, applies rules, optionally sends remaining descriptions to OpenAI, and inserts the transactions into PostgreSQL.
8. Review and correct categories from `/transactions`.

Uploaded files are saved under `UPLOAD_DIR`, which defaults to `storage/uploads`. Treat uploaded bank files as sensitive personal data. In a production deployment, use persistent storage if uploaded files must survive redeployments.

## Main API areas

The application exposes authenticated API routes for the following operations:

### Transactions

- `GET /api/transactions` — list transactions with filters and pagination.
- `GET /api/transactions/count` — count filtered transactions.
- `GET /api/transactions/filters` — retrieve available categories and accounts.
- `PATCH /api/transactions/{transaction_id}` — manually update a category.
- `PATCH /api/transactions/bulk-category` — update several categories.
- `POST /api/transactions/{transaction_id}/split` — split a transaction.
- `GET /api/transactions/{transaction_id}/split` — retrieve split rows.
- `DELETE /api/transactions/{transaction_id}/split` — remove splits.
- `POST /api/transactions/{transaction_id}/revert-auto` — mark a category as automatic again.

### Rules

- `GET /api/rules` — list the current user's rules.
- `POST /api/rules` — create a rule.
- `DELETE /api/rules/{rule_id}` — delete a rule.
- `GET /api/rules/preview-rerun` — preview rule-based changes.
- `POST /api/rules/apply-rerun` — apply rule-based changes.

### Uploads

- `POST /api/uploads` — upload and process one or more transaction files.

### Net worth

- `GET /api/networth/dashboard` — retrieve accounts, valuations, snapshots, and lookup data.
- `/api/networth/lookups` — manage institutions, asset categories, account types, currencies, and liquidity statuses.
- `/api/networth/accounts` — manage net-worth accounts.
- `/api/networth/valuations` — manage account valuations.
- `/api/networth/snapshots` — manage historical snapshots.
- `POST /api/networth/compute-snapshot` — compute current totals from the latest valuations.

All application data queries are scoped to the authenticated user's ID.

## Testing and development checks

Before committing changes, run a syntax check across the project:

```bash
python -m compileall app categorizers legacy_db models parsers utils
```

Start the application locally and verify:

1. The process starts without import or database errors.
2. `/login` and `/register` load.
3. An approved user can log in and reach `/`.
4. Static CSS loads from `/static`.
5. A small test transaction file can be uploaded.
6. Manual category changes persist after refreshing.
7. Rules and net-worth data are isolated between users.

For production changes, test database migrations against a copy of the database first. The current startup table creation is not a replacement for a versioned migration system.

## Railway deployment

### 1. Create or connect the project

1. Push the repository to GitHub.
2. Create a Railway project and deploy the repository as a service.
3. Provision a PostgreSQL service in the same Railway project.
4. Link the application service and PostgreSQL service if you want to use Railway variable references.

### 2. Configure Railway variables

Add the database variables required by `app/core/config.py`:

```text
DB_USER
DB_PASSWORD
DB_HOST
DB_PORT
DB_NAME
```

Railway may provide a `DATABASE_URL` variable, but this application currently constructs its own URL from the five `DB_*` variables. Map the Railway PostgreSQL values to those names, or update the configuration code to consume `DATABASE_URL` consistently before deploying.

Also add:

```text
APP_SECRET_KEY=<long-random-production-secret>
SESSION_COOKIE_NAME=expense_tracker_session
UPLOAD_DIR=storage/uploads
ENABLE_LLM_CATEGORIZATION=true
OPENAI_API_KEY=<production-openai-key>
```

Do not paste secrets into source files or commit them to GitHub.

### 3. Set the start command

Because `main.py` is inside `app/`, use:

```bash
PYTHONPATH=. uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

The `$PORT` value is supplied by Railway. Do not hard-code port `8000` in the production start command. Railway's public networking configuration must target the port on which Uvicorn is actually listening.

### 4. Verify the deployment

Healthy logs should include messages indicating that the tables are ready and that Uvicorn is running on `0.0.0.0:$PORT`.

If the deployment fails, diagnose the first meaningful exception in the logs:

- `No module named ...` usually indicates a missing committed package/file or an incorrect module path.
- `invalid literal for int() ... None` usually indicates a missing `DB_PORT` or another malformed database variable.
- `libpq.so.5` usually indicates the wrong PostgreSQL driver package or a deployment image missing PostgreSQL client libraries; use `psycopg2-binary` in the requirements unless you intentionally configure system libraries.
- `Missing credentials` from OpenAI means `OPENAI_API_KEY` is not available to the Railway service.
- `502 Bad Gateway` commonly means the service is not listening on Railway's assigned `$PORT`, or the service has not been publicly exposed.

### 5. Generate a domain

After the service is healthy, generate a Railway public domain for the web service. Open the generated HTTPS address in a browser and use `/register` or `/login`.

Railway's filesystem may be ephemeral between deployments. PostgreSQL is the persistent location for application records; do not rely on files under `storage/` as the only copy of uploaded documents.

## Database migration

The application uses PostgreSQL locally and in production, so a PostgreSQL-to-PostgreSQL migration is preferable to copying a SQLite file.

A safe migration workflow is:

1. Back up the local database.
2. Confirm the Railway database schema exists.
3. Register the production user, or decide whether to migrate the local user record and password hash.
4. Export the required local tables with `pg_dump` or a database GUI.
5. Import into Railway PostgreSQL in foreign-key order.
6. Verify row counts and ownership IDs.
7. Verify manual transaction categories and split rows.
8. Verify net-worth accounts, valuations, and snapshots.
9. Only remove or overwrite data after checking the imported copy.

The core table order is generally:

```text
users
category_rules
transactions
transaction_splits
networth_institutions
networth_asset_categories
networth_account_types
networth_currencies
networth_liquidity_statuses
networth_accounts
networth_valuations
networth_snapshots
```

Because rows contain `user_id` references, changing user IDs during migration can detach data from the intended account. Preserve IDs where possible, or update every dependent table consistently in a transaction. Always back up both databases before importing.

For a full PostgreSQL database dump, use the PostgreSQL client tools rather than SQLite commands:

```bash
pg_dump --format=custom --file=expense_tracker.dump "$LOCAL_DATABASE_URL"
pg_restore --no-owner --clean --if-exists --dbname="$RAILWAY_DATABASE_URL" expense_tracker.dump
```

Use the connection strings appropriate for your environment. Do not put either connection string into this README, Git history, screenshots, or issue reports.

If you use Railway's private network, a local Railway CLI tunnel can be used for a database GUI. Keep the tunnel open while DBeaver or another client is connected.

## Backups and privacy

This application processes financial data, uploaded bank files, and authentication data. Recommended practices:

- Keep PostgreSQL backups enabled.
- Maintain an additional encrypted backup before migrations.
- Do not commit uploaded files or database dumps.
- Use strong, unique database and application secrets.
- Rotate credentials after sharing access with another person or tool.
- Restrict administrator access.
- Review OpenAI data and usage settings before sending transaction descriptions for categorization.
- Use HTTPS for production access.

## Troubleshooting

### The browser shows `{"detail":"Not authenticated"}`

The requested page is protected by the session dependency. Use `/login`. If the root page should redirect unauthenticated visitors, ensure the root route catches the authentication exception and returns a redirect to `/login`.

### The app cannot import `legacy_db`

Confirm that `legacy_db/` is committed to GitHub and is not ignored as an entire directory. It contains Python database code, not merely a database file. Add an empty `legacy_db/__init__.py` if your packaging/import setup requires it, then deploy again from the repository root.

### The app starts but cannot connect to PostgreSQL

Check all five `DB_*` variables, the host/port visibility, the database password, and whether the selected host is private-only. From a local machine, use a Railway tunnel or a secured public connection for database tools. Never expose the connection string in a public repository.

### OpenAI categorization is unavailable

Check that `OPENAI_API_KEY` is set in the same environment as the running service and that `ENABLE_LLM_CATEGORIZATION` is configured as intended. If the key is rotated, update the local `.env` or Railway variable and restart/redeploy the service.

## License

No license has been specified yet. Until a license is added to this repository, assume that the source is not available for redistribution or commercial reuse without the author's permission.
