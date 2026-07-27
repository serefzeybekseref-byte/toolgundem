from dotenv import load_dotenv
load_dotenv()
from db_target import print_db_target, guard_postgres
print_db_target()
guard_postgres()
import db
from collections import Counter

conn = db.get_connection()
rows = conn.execute("SELECT id, slug, related_tool_slugs FROM guides WHERE related_topic IS NULL OR related_topic=''").fetchall()

updated = 0
skipped = []
for r in rows:
    d = dict(r)
    slugs = [s.strip() for s in (d["related_tool_slugs"] or "").split(",") if s.strip()]
    if not slugs:
        skipped.append(d["slug"])
        continue
    placeholders = ",".join(["?"] * len(slugs))
    prods = conn.execute(f"SELECT topics FROM products WHERE slug IN ({placeholders})", tuple(slugs)).fetchall()
    counter = Counter()
    for p in prods:
        topics = dict(p).get("topics") or ""
        for t in topics.split(","):
            t = t.strip()
            if t:
                counter[t] += 1
    if not counter:
        skipped.append(d["slug"])
        continue
    best_topic = counter.most_common(1)[0][0]
    conn.execute("UPDATE guides SET related_topic = ? WHERE id = ?", (best_topic, d["id"]))
    conn.commit()
    updated += 1
    print(f"[{d['slug']}] -> {best_topic}")

print(f"\nGuncellendi: {updated}, atlandi: {len(skipped)}")
if skipped:
    print("atlananlar:", skipped)
conn.close()
