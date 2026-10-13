import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import db
db.init_db()
db.upsert_channel({
    "youtube_name": "Test Channel",
    "niche": "Gadget Review",
    "google_api_1": "AIzaSyDavTA2tJ0-ViDOVJy3cKWbbxhb5d8kucM",
    "enabled": 1
})
print("Channel seeded via app.db.upsert_channel")
