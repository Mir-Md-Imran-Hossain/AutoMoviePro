from app import db as store

with store.db() as conn:
    rows = conn.execute(
        """
        SELECT id, video_type, customer_state,
               substr(coalesce(error, ''), 1, 240) AS err,
               local_path
        FROM jobs
        WHERE requested_by = ?
        ORDER BY id DESC
        LIMIT 5
        """,
        ("c11_marathon_customer",),
    ).fetchall()
    for r in rows:
        print(dict(r))
