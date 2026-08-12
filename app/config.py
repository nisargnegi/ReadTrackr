import os
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data" if Path("/app").exists() else "data"))
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'readtrackr.db'}")
APP_USERNAME = os.getenv("APP_USERNAME", "admin")
APP_PASSWORD_HASH = os.getenv("APP_PASSWORD_HASH", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "development-only-change-me")
GOOGLE_BOOKS_API_KEY = os.getenv("GOOGLE_BOOKS_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
