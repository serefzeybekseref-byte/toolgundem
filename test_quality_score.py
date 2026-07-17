from dotenv import load_dotenv
load_dotenv()
import db

conn = db.get_connection()
row = conn.execute("SELECT * FROM products ORDER BY created_at DESC LIMIT 1").fetchone()
row = dict(row)
conn.close()

print("secilen urun:", row["title_tr"])
print("summary_tr dolu mu:", bool((row.get("summary_tr") or "").strip()))
print("website:", row.get("website"))
print("topics:", row.get("topics"))
print("platforms:", row.get("platforms"))

score = db.compute_quality_score(row)
print("compute_quality_score sonucu:", score)

result = db.update_quality_score(row["id"], row)
print("update_quality_score donen deger:", result)

conn2 = db.get_connection()
after = conn2.execute("SELECT quality_score FROM products WHERE id = ?", (row["id"],)).fetchone()
conn2.close()
print("DB'de yeni deger:", dict(after)["quality_score"])
