# LAN Unit Management

Flask application for managing personnel, duties, leave, equipment, and schedules on a local network.

## Requirements

- Windows, Linux, or macOS
- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) (recommended)

If `uv` was installed with `py -3.10 -m pip install --user uv` and is not yet on `PATH`, replace `uv` in the commands below with `py -3.10 -m uv` or open a new terminal.

## First-time setup

```powershell
uv sync --extra dev
Copy-Item .env.example .env
```

Replace `SESSION_SECRET` in `.env` with a random value. For production, keep `APP_ENV=production`.

Create or update the database schema:

```powershell
uv run flask --app app db upgrade
```

Create the first user (the password prompt does not echo or save the password):

```powershell
uv run flask --app app create-user
```

Optional demo data:

```powershell
uv run flask --app app seed-demo
```

## Run

The default command uses Waitress rather than Flask's development server:

```powershell
uv run python main.py
```

Open <http://127.0.0.1:5000>. Other devices on the LAN can use the server computer's LAN IP address.

To intentionally use Flask debug mode during local development:

```powershell
$env:APP_ENV = "development"
$env:FLASK_DEBUG = "true"
uv run python main.py
```

Never enable debug mode on a shared network.

## Database maintenance

Apply schema migrations after pulling application updates:

```powershell
uv run flask --app app db upgrade
```

Create a consistent, timestamped SQLite backup:

```powershell
uv run flask --app app backup-db
```

Backups are written to `backups/` and ignored by Git. Copy them to separate protected storage. If `DATABASE_URL` points to PostgreSQL, use `pg_dump` instead.

Change an existing password:

```powershell
uv run flask --app app set-password USERNAME
```

## PostgreSQL

SQLite is appropriate for a small deployment with light concurrent writing. For heavier multi-user use, create a PostgreSQL database and set:

```text
DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@HOST/DATABASE
```

Then run `uv run flask --app app db upgrade`.

## Tests

```powershell
uv run pytest
```

The test suite uses an isolated in-memory database and does not modify the application database.

## Security notes

- Secrets and passwords are not stored in tracked source files.
- The sample login credentials were removed from the login page.
- All application screens require authentication.
- Set `COOKIE_SECURE=true` when serving the application through HTTPS.
- Set `TRUSTED_PROXY_COUNT=1` only when one trusted reverse proxy is in front of the app.
