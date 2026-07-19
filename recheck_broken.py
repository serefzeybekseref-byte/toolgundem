from dotenv import load_dotenv
load_dotenv()
from db import get_connection, mark_link_checked
from check_links import check_url
import time

conn = get_connection()
rows = conn.execute("SELECT id, original_name, website, ph_url FROM products WHERE is_broken = 1").fetchall()
rows = [dict(r) for r in rows]
conn.close()
print(f"{len(rows)} kirik isaretli urun yeniden test ediliyor...")

for r in rows:
    website = r.get("website") or r.get("ph_url")
    is_up, reason = check_url(website)
    mark_link_checked(r["id"], is_broken=not is_up, reason=reason)
    status = "DUZELDI" if is_up else f"hala kirik ({reason})"
    print(f"  {r['original_name']}: {status}")
    time.sleep(0.5)
