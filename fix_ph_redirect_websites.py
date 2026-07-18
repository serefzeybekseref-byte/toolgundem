from dotenv import load_dotenv
load_dotenv()
import os
import requests
import db

TOKEN = os.getenv("PRODUCTHUNT_TOKEN")
API_URL = "https://api.producthunt.com/v2/api/graphql"

QUERY = """
query($id: ID!) {
  post(id: $id) {
    id
    name
    website
    url
  }
}
"""

conn = db.get_connection()
rows = conn.execute(
    "SELECT id, ph_id, original_name, website FROM products WHERE is_broken = 1"
).fetchall()

headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
fixed = 0
for r in rows:
    d = dict(r)
    if d["website"] and "producthunt.com/r/" not in d["website"]:
        continue  # bu zaten gercek domain, PH yonlendirme sorunu degil
    resp = requests.post(API_URL, json={"query": QUERY, "variables": {"id": d["ph_id"]}}, headers=headers)
    data = resp.json()
    post = data.get("data", {}).get("post")
    if post and post.get("website"):
        real_website = post["website"]
        conn.execute("UPDATE products SET website = ? WHERE id = ?", (real_website, d["id"]))
        print(f"DUZELTILDI: {d['original_name']} -> {real_website}")
        fixed += 1
    else:
        print(f"BULUNAMADI: {d['original_name']} (ph_id={d['ph_id']}) - PH'de website alani bos/urun kaldirilmis olabilir")

conn.commit()
conn.close()
print(f"\nToplam duzeltilen: {fixed}")
