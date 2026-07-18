from dotenv import load_dotenv
load_dotenv()
import db
conn = db.get_connection()
row = conn.execute("SELECT id, slug FROM products WHERE original_name = ?", ("Tome",)).fetchone()
if row:
    d = dict(row)
    conn.execute("DELETE FROM products WHERE id = ?", (d["id"],))
    print(f"Silindi (urun artik yok, Nisan 2025'te kapandi): Tome (slug={d['slug']})")
conn.commit()
conn.close()
