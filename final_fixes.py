from dotenv import load_dotenv
load_dotenv()
import db
conn = db.get_connection()

# Bonacci Studio: gercek (bosluksuz) domain calisiyor, guncelle + kirik isaretini kaldir
row = conn.execute("SELECT id FROM products WHERE original_name = ?", ("Bonacci Studio ",)).fetchone()
if row:
    pid = dict(row)["id"]
    conn.execute(
        "UPDATE products SET website = ?, is_broken = 0 WHERE id = ?",
        ("https://studio.bonacci.thinkingdbx.com/", pid)
    )
    print("Bonacci Studio duzeltildi.")

# 4400mm Corrugated Paper Machine: AI araci degil, sanayi makinesi - filtre acigindan sizmis, sil
row2 = conn.execute("SELECT id, slug FROM products WHERE original_name = ?", ("4400mm Corrugated Paper Machine",)).fetchone()
if row2:
    d2 = dict(row2)
    conn.execute("DELETE FROM products WHERE id = ?", (d2["id"],))
    print(f"Silindi (AI araci degil): 4400mm Corrugated Paper Machine (slug={d2['slug']})")

conn.commit()
conn.close()
