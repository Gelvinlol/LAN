import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

import click
from dotenv import load_dotenv
from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash

load_dotenv()


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
migrate = Migrate()
app = Flask(__name__)

environment = os.environ.get("APP_ENV", "development").lower()
secret_key = os.environ.get("SESSION_SECRET")
if environment == "production" and not secret_key:
    raise RuntimeError("SESSION_SECRET must be set when APP_ENV=production")

app.config.update(
    SECRET_KEY=secret_key or "development-only-secret-change-me",
    SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", "sqlite:///military_unit.db"),
    SQLALCHEMY_ENGINE_OPTIONS={"pool_recycle": 300, "pool_pre_ping": True},
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
)

proxy_count = int(os.environ.get("TRUSTED_PROXY_COUNT", "0"))
if proxy_count:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxy_count, x_proto=proxy_count, x_host=proxy_count)

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
)

db.init_app(app)
migrate.init_app(app, db, render_as_batch=True)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Παρακαλώ συνδεθείτε για να προσπελάσετε αυτή τη σελίδα."
login_manager.login_message_category = "info"


@login_manager.user_loader
def load_user(user_id):
    from models import User

    return db.session.get(User, int(user_id))


# Import models before routes so migration discovery sees all tables.
import models  # noqa: E402, F401
from routes import *  # noqa: E402, F403


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


@app.cli.command("create-user")
@click.option("--username", prompt=True)
@click.option("--full-name", prompt=True)
@click.option("--role", prompt=True)
@click.password_option(confirmation_prompt=True)
def create_user(username, full_name, role, password):
    """Create a user without storing a password in source code."""
    from models import User

    if User.query.filter_by(username=username).first():
        raise click.ClickException(f"User '{username}' already exists")
    db.session.add(User(
        username=username,
        full_name=full_name,
        role=role,
        password_hash=generate_password_hash(password),
    ))
    db.session.commit()
    click.echo(f"Created user '{username}'.")


@app.cli.command("set-password")
@click.argument("username")
@click.password_option(confirmation_prompt=True)
def set_password(username, password):
    """Set a user's password interactively."""
    from models import User

    user = User.query.filter_by(username=username).first()
    if not user:
        raise click.ClickException(f"User '{username}' does not exist")
    user.password_hash = generate_password_hash(password)
    db.session.commit()
    click.echo(f"Updated password for '{username}'.")


@app.cli.command("seed-demo")
@click.option("--soldiers", default=50, show_default=True, type=click.IntRange(0, 500))
def seed_demo(soldiers):
    """Add non-sensitive duty types and optional demo soldiers."""
    import random
    from datetime import date, timedelta
    from models import DutyType, Soldier

    duties = [
        {"name": "Περίπολος", "description": "Patrol duty", "team_size": 2, "shifts_per_day": 3},
        {"name": "Κεντρική Πύλη", "description": "Main Gate duty", "team_size": 2, "shifts_per_day": 3},
        {"name": "Θαλαμοφύλακας", "description": "Dorm Watch duty", "team_size": 1, "shifts_per_day": 3},
        {"name": "Μαγειρεία", "description": "Cookhouse duty", "team_size": 3, "shifts_per_day": 1},
        {"name": "Λάντζα", "description": "Dishwashing duty", "team_size": 2, "shifts_per_day": 1},
    ]
    for duty in duties:
        if not DutyType.query.filter_by(name=duty["name"]).first():
            db.session.add(DutyType(**duty))

    first_names = ["Αλέξανδρος", "Δημήτριος", "Γιάννης", "Νικόλαος", "Κωνσταντίνος", "Μιχάλης"]
    last_names = ["Παπαδόπουλος", "Παπαγιάννης", "Κωνσταντίνου", "Γεωργίου", "Δημητρίου", "Νικολάου"]
    specialties = ["Πεζικό", "Τεχνικός", "Διαβιβάσεις", "Μηχανικός", "Οδηγός", "Μάγειρας"]

    added = 0
    for _ in range(soldiers):
        military_id = f"{random.randint(2020, 2026)}{random.randint(100000, 999999)}"
        while Soldier.query.filter_by(military_id=military_id).first():
            military_id = f"{random.randint(2020, 2026)}{random.randint(100000, 999999)}"
        db.session.add(Soldier(
            name=f"{random.choice(first_names)} {random.choice(last_names)}",
            military_id=military_id,
            enlistment_date=date.today() - timedelta(days=random.randint(30, 730)),
            specialty=random.choice(specialties),
            status="Active",
        ))
        added += 1
    db.session.commit()
    click.echo(f"Seeded duty types and {added} demo soldiers.")


@app.cli.command("backup-db")
@click.option("--output-dir", default="backups", show_default=True, type=click.Path())
def backup_db(output_dir):
    """Create a timestamped, consistent backup of the SQLite database."""
    database_url = db.engine.url
    if database_url.drivername != "sqlite":
        raise click.ClickException("For PostgreSQL, use pg_dump rather than this SQLite backup command.")

    source = Path(database_url.database).resolve()
    if not source.exists():
        raise click.ClickException(f"Database does not exist: {source}")
    destination_dir = Path(output_dir).resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"military_unit-{datetime.now():%Y%m%d-%H%M%S}.db"

    import sqlite3

    with sqlite3.connect(source) as source_db, sqlite3.connect(destination) as backup:
        source_db.backup(backup)
    shutil.copystat(source, destination)
    click.echo(str(destination))
