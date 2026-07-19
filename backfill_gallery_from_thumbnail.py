# -*- coding: utf-8 -*-
"""
Gallery bos olan (ekran goruntusu bolumu bombos gorunen) urunler icin,
gercek/favicon-olmayan thumbnail'i tek bir galeri ogesi olarak kullanir.
Bu, save_product() icindeki YENI mantiga (bkz. db.py) gecmis kayitlar icin
bir kerelik uygulanmasidir - ileride eklenen urunler zaten otomatik kapsanir.
"""
from dotenv import load_dotenv
load_dotenv()


def main():
    from db import get_connection

    conn = get_connection()
    rows = conn.execute("""
        SELECT id, original_name, thumbnail FROM products
        WHERE (gallery IS NULL OR gallery = '')
        AND thumbnail IS NOT NULL AND thumbnail != ''
        AND thumbnail NOT LIKE ?
    """, ("%google.com/s2/favicons%",)).fetchall()
    rows = [dict(r) for r in rows]
    print(f"{len(rows)} urun gallery'siz ama gercek thumbnail'i var, dolduruluyor...")

    for r in rows:
        conn.execute("UPDATE products SET gallery = ? WHERE id = ?", (r["thumbnail"], r["id"]))

    conn.commit()
    conn.close()
    print(f"Tamamlandi. {len(rows)} urune galeri (thumbnail'den) atandi.")


if __name__ == "__main__":
    main()
