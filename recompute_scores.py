from dotenv import load_dotenv
load_dotenv()
import db

updated = db.recompute_all_quality_scores()
print("guncellenen urun sayisi:", updated)

conn = db.get_connection()
avg = conn.execute("SELECT AVG(quality_score) as a FROM products").fetchone()
high = conn.execute("SELECT COUNT(*) as c FROM products WHERE quality_score >= 70").fetchone()
zero = conn.execute("SELECT COUNT(*) as c FROM products WHERE quality_score = 0").fetchone()
conn.close()
print("yeni ortalama:", dict(avg)["a"])
print("yuksek kalite (>=70):", dict(high)["c"])
print("hala 0 olan:", dict(zero)["c"])
