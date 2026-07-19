"""
Mevcut tum urunler icin quality_score'u (deterministik tamlik puani) hesaplayip kaydeder.
Yeni eklenen urunlerde bu zaten save_product() icinde otomatik hesaplaniyor;
bu script sadece gecmis kayitlari (quality_score eklenmeden once
eklenmis olanlari) guncellemek icindir.

Kullanim: python backfill_quality_score.py
"""
from dotenv import load_dotenv
load_dotenv()
from db_target import print_db_target, guard_postgres
print_db_target()
guard_postgres()
from db import init_db, recompute_all_quality_scores

if __name__ == "__main__":
    init_db()
    count = recompute_all_quality_scores()
    print(f"Tamamlandi. {count} urunun quality_score'u guncellendi.")
