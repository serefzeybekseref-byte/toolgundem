from dotenv import load_dotenv
load_dotenv()
import db
import app as a

conn = db.get_connection()
rows = conn.execute("SELECT topics FROM products WHERE topics IS NOT NULL AND topics != ''").fetchall()
conn.close()

all_topics = {}
for r in rows:
    for t in dict(r)["topics"].split(","):
        t = t.strip()
        if t:
            all_topics[t] = all_topics.get(t, 0) + 1

missing = {t: c for t, c in all_topics.items() if t not in a.TOPIC_LABELS}
missing_sorted = sorted(missing.items(), key=lambda x: -x[1])

print(f"Toplam benzersiz kategori: {len(all_topics)}")
print(f"TOPIC_LABELS'ta olmayan (cevrilmemis): {len(missing)}\n")
for t, c in missing_sorted:
    print(f"  {t!r}: {c} urun")
