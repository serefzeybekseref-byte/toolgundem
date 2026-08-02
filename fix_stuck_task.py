from dotenv import load_dotenv
load_dotenv()
import db
from automation_pipeline import _recover_stuck_running_tasks

conn = db.get_connection()
_recover_stuck_running_tasks(conn)
conn.close()

conn2 = db.get_connection()
stuck = conn2.execute("SELECT id, task_type, status FROM content_tasks WHERE id = ?", (350,)).fetchone()
conn2.close()
print("gorev 350 yeni durumu:", dict(stuck))
