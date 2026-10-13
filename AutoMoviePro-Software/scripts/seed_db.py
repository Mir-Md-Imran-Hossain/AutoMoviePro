import sqlite3
import os

db_path = 'E:/All Project/AutoMovie_Pro_SAAS_Final_Update/AutoMoviePro-Software/data/local.db'
os.makedirs(os.path.dirname(db_path), exist_ok=True)
conn = sqlite3.connect(db_path)
conn.execute('CREATE TABLE IF NOT EXISTS channels (id TEXT PRIMARY KEY, name TEXT, niche TEXT, google_api_1 TEXT, intro_path TEXT, logo_path TEXT)')
conn.execute('INSERT OR REPLACE INTO channels (id, name, niche, google_api_1) VALUES ("test_ch", "Test Channel", "Gadget Review", "AIzaSyDavTA2tJ0-ViDOVJy3cKWbbxhb5d8kucM")')
conn.commit()
conn.close()
print("Channel seeded successfully.")
