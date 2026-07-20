"""
Trending Vote Refresh: en cok oy alan (top N) urunlerin Product Hunt oy sayisini
guncel tutar. 436+ urunun tamamini cekmek gereksiz oldugu icin sadece en gorunur
(en cok trafik alan) top-N urun haftalik olarak guncellenir.
"manual-" ph_id'li urunler (bulk_seed ile eklenenler) gercek PH kaydi olmadigi
icin atlanir.

Kullanim:
    python refresh_trending_votes.py         -> top 100
    python refresh_trending_votes.py 50      -> top 50
"""
import sys
import time
from dotenv import load_dotenv
load_dotenv()

import db
from fetch_producthunt import get_post_votes

SLEEP_BETWEEN = 0.4


def run(limit: int = 100):
    conn = db.get_connection()
    rows = conn.execute("""
        SELECT id, ph_id, title_tr, votes FROM products
        WHERE ph_id NOT LIKE ?
        ORDER BY votes DESC LIMIT ?
    """, ("manual-%", limit)).fetchall()
    rows = [dict(r) for r in rows]
    conn.close()

    updated, unchanged, failed = 0, 0, 0
    for r in rows:
        try:
            new_votes = get_post_votes(r["ph_id"])
        except Exception as e:
            print(f"  [HATA] {r['title_tr']}: {e}")
            failed += 1
            time.sleep(SLEEP_BETWEEN)
            continue

        if new_votes is None:
            failed += 1
            time.sleep(SLEEP_BETWEEN)
            continue

        if new_votes != r["votes"]:
            conn2 = db.get_connection()
            conn2.execute("UPDATE products SET votes = ? WHERE id = ?", (new_votes, r["id"]))
            conn2.commit()
            conn2.close()
            print(f"  [guncellendi] {r['title_tr']}: {r['votes']} -> {new_votes}")
            updated += 1
        else:
            unchanged += 1
        time.sleep(SLEEP_BETWEEN)

    print(f"\nTamamlandi. Guncellenen: {updated}, Degismeyen: {unchanged}, Hatali/kaldirilmis: {failed}, Toplam: {len(rows)}")


if __name__ == "__main__":
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    run(limit=lim)
