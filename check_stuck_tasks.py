from dotenv import load_dotenv
load_dotenv()
import db

conn = db.get_connection()
stuck = conn.execute("SELECT id, task_type, status, started_at FROM content_tasks WHERE status = 'RUNNING'").fetchall()
conn.close()
stuck = [dict(r) for r in stuck]
print("RUNNING durumunda takili gorev sayisi:", len(stuck))
for s in stuck:
    print(" ", s)
