from app.customer_job import get_job
from app import db as store

with store.db() as conn:
    rows = conn.execute(
        "SELECT id,video_type,customer_state,substr(error,1,200) as err,local_path FROM jobs WHERE requested_by=? ORDER BY id DESC LIMIT 8",
        ("c11_marathon_customer",),
    ).fetchall()
    for r in rows:
        print(dict(r))
