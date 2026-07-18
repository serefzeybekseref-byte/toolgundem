from dotenv import load_dotenv
load_dotenv()
from fetch_producthunt import get_latest_products
import db

conn = db.get_connection()
latest = get_latest_products(max_products=20)
updated = 0
for p in latest:
    if not p.get("gallery"):
        continue
    row = conn.execute("SELECT id FROM products WHERE ph_id = ?", (p["id"],)).fetchone()
    if row:
        pid = dict(row)["id"]
        conn.execute("UPDATE products SET gallery = ? WHERE id = ?", (",".join(p["gallery"]), pid))
        updated += 1
conn.commit()
conn.close()
print(f"Geriye donuk guncellenen urun: {updated}")
