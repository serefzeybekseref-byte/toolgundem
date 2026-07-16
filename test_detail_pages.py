from dotenv import load_dotenv
load_dotenv()
import db
comps = db.get_all_comparisons()
print("comparison slug ornek:", comps[0]["slug"] if comps else None)
cols = db.get_all_collections()
print("collection slug ornek:", cols[0]["slug"] if cols else None)
import app as a
c = a.app.test_client()
if comps:
    r = c.get("/karsilastirma/" + comps[0]["slug"])
    print("comparison detail ->", r.status_code)
if cols:
    r = c.get("/koleksiyon/" + cols[0]["slug"])
    print("collection detail ->", r.status_code)
    col_full = db.get_collection_by_slug(cols[0]["slug"])
    print("collection items sayisi:", len(col_full["items"]))
