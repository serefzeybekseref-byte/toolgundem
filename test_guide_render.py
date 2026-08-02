from dotenv import load_dotenv
load_dotenv()
import db
import app as a

conn = db.get_connection()
row = conn.execute("SELECT slug FROM guides WHERE title LIKE ?", ("%Cursor ve Alternatifleri%",)).fetchone()
conn.close()
slug = dict(row)["slug"]
print("slug:", slug)

c = a.app.test_client()
r = c.get(f"/rehber/{slug}")
print("status:", r.status_code)
body = r.get_data(as_text=True)
print("karsilastirma linki var mi:", "ai-kod-asistanlari" in body)
