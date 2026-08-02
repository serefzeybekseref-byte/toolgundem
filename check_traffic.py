from dotenv import load_dotenv
load_dotenv()
import db

stats = db.get_visit_stats()
print("ziyaret istatistikleri:", stats)

subs = db.get_all_subscribers()
active = [s for s in subs if s.get("is_active")]
print("toplam abone:", len(subs), "| aktif:", len(active))

admin = db.get_admin_stats()
print("admin stats:", admin)
