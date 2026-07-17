from dotenv import load_dotenv
load_dotenv()
import db
conn = db.get_connection()

cols = conn.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'products'
""").fetchall()
print("kolonlar:", [dict(c)["column_name"] for c in cols])

dist = conn.execute("""
    SELECT quality_score, COUNT(*) as c FROM products
    GROUP BY quality_score ORDER BY quality_score
""").fetchall()
print("skor dagilimi:")
for d in dist:
    d = dict(d)
    print(" ", d["quality_score"], "->", d["c"])

null_score = conn.execute("SELECT COUNT(*) as c FROM products WHERE quality_score IS NULL").fetchone()
print("quality_score NULL olanlar:", dict(null_score)["c"])

recent = conn.execute("SELECT title_tr, created_at, quality_score, platforms FROM products ORDER BY created_at DESC LIMIT 10").fetchall()
print("son eklenen 10 urun:")
for r in recent:
    r = dict(r)
    print(" ", r["created_at"], "|", r["title_tr"], "| skor:", r["quality_score"], "| platforms:", r["platforms"])

conn.close()
