import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
USERBOT_SESSION = os.getenv("USERBOT_SESSION", "checkthamgia")
ADMIN_IDS: list[int] = [
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
]
DB_PATH = os.getenv("DB_PATH", str(DATA_DIR / "clender.db"))
BACKUP_INTERVAL_HOURS = int(os.getenv("BACKUP_INTERVAL_HOURS", "6"))
SESSION_PATH = DATA_DIR / USERBOT_SESSION

# Broadcast: chờ bao lâu không có tin mới trước khi hỏi xác nhận (giây)
BROADCAST_IDLE_SECONDS = float(os.getenv("BROADCAST_IDLE_SECONDS", "1.0"))
