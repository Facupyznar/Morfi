import os
from pathlib import Path
from urllib.parse import quote_plus


def _load_local_env():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for raw_line in env_path.read_text().splitlines():
            line = raw_line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def _build_database_uri():
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return database_url

    db_user = os.environ.get("DB_USER")
    db_password = os.environ.get("DB_PASSWORD")
    db_name = os.environ.get("DB_NAME")
    db_host = os.environ.get("DB_HOST", "localhost")
    db_port = os.environ.get("DB_PORT", "5432")

    if not all([db_user, db_password, db_name]):
        return None

    return f"postgresql+psycopg2://{quote_plus(db_user)}:{quote_plus(db_password)}@{db_host}:{db_port}/{quote_plus(db_name)}"


_load_local_env()


class Config:
    SQLALCHEMY_DATABASE_URI = _build_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev_key_morfi")
    WTF_CSRF_TIME_LIMIT = None

    # Flask-Mail (Gmail SMTP)
    MAIL_SERVER         = "smtp.gmail.com"
    MAIL_PORT           = 587
    MAIL_USE_TLS        = True
    MAIL_USERNAME       = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD       = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = ("Morfi", os.environ.get("MAIL_USERNAME", "noreply@morfi.app"))

    # Gemini AI
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

    # Google OAuth (login social para comensales)
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
    # Redirect URI opcional. Si no se define, se construye con url_for(..., _external=True).
    # En dev suele ser http://localhost:5000/login/google/callback
    GOOGLE_OAUTH_REDIRECT_URI = os.environ.get("GOOGLE_OAUTH_REDIRECT_URI")

    # Google Contacts (People API) — scope sensible pedido por autorización
    # incremental SOLO al tocar "Encontrá amigos", nunca en el login.
    GOOGLE_CONTACTS_REDIRECT_URI = os.environ.get("GOOGLE_CONTACTS_REDIRECT_URI")
    # Incluir "otros contactos" (gente con la que interactuó pero no guardó).
    GOOGLE_CONTACTS_INCLUDE_OTHER = (
        os.environ.get("GOOGLE_CONTACTS_INCLUDE_OTHER", "false").strip().lower()
        in {"1", "true", "yes", "on"}
    )