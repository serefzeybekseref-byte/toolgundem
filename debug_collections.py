from dotenv import load_dotenv
load_dotenv()
import db

conn = db.get_connection()
cols = conn.execute("SELECT id, slug FROM collections").fetchall()
print("collections tablosu:", [dict(c) for c in cols])

items = conn.execute("SELECT * FROM collection_items").fetchall()
print("collection_items satir sayisi:", len(items))
for it in items[:5]:
    print(dict(it))
conn.close()
