from dotenv import load_dotenv
load_dotenv()
import db
conn = db.get_connection()
tables = conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'").fetchall()
print([dict(t)["table_name"] for t in tables])
conn.close()
