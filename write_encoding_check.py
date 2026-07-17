from dotenv import load_dotenv
load_dotenv()
import db
conn = db.get_connection()
recent = conn.execute("SELECT title_tr FROM products ORDER BY created_at DESC LIMIT 10").fetchall()
conn.close()
with open("encoding_check.txt", "w", encoding="utf-8") as f:
    for r in recent:
        f.write(dict(r)["title_tr"] + "\n")
print("yazildi")
