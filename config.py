import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "database" / "rely.db"
SECRET_KEY = os.getenv("SECRET_KEY", "rely-secret-key-change-me")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "hemanathanarish0@gmail.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "RELYAdmin@2026")
