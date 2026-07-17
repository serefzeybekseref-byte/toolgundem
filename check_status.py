from dotenv import load_dotenv
load_dotenv()
import db
conn = db.get_connection()
total = conn.execute("SELECT COUNT(*) as c FROM products").fetchone()
filled = conn.execute("SELECT COUNT(*) as c FROM products WHERE platforms IS NOT NULL AND platforms != ''").fetchone()
high = conn.execute("SELECT COUNT(*) as c FROM products WHERE quality_score >= 70").fetchone()
avg = conn.execute("SELECT AVG(quality_score) as a FROM products").fetchone()
conn.close()
print("toplam:", dict(total)["c"])
print("platforms dolu:", dict(filled)["c"])
print("yuksek kalite (>=70):", dict(high)["c"])
print("ortalama skor:", dict(avg)["a"])
