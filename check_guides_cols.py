from dotenv import load_dotenv
load_dotenv()
import db
conn = db.get_connection()
cols = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'guides'").fetchall()
print([dict(c)["column_name"] for c in cols])
conn.close()
