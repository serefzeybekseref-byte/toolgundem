import sys
import argparse
import re
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()
from db import get_connection, init_db
from content_intelligence import discover_opportunities

# Bir gorev basarisiz oldugunda, hatanin GECICI ALTYAPI sorunu (kota/rate-limit/timeout)
# mu yoksa GERCEK ICERIK sorunu (kalite kapisi, uydurma bilgi vb.) mu oldugunu ayirt
# ederiz. Gecici olanlari PENDING'e geri dondururuz ki bir sonraki calistirmada
# (bos/az yogun saatlerde) otomatik tekrar denensin - bunlari sonsuza kadar
# FAILED birakmak, kota dolu oldugu icin basarisiz olan gorevleri bir daha asla
# denenmeyecek sekilde "kaybetmek" anlamina geliyordu (30 Temmuz 2026'da 8/10
# rehberin bu yuzden elle tekrar calistirilmasi gerekmisti).
_TRANSIENT_ERROR_PATTERNS = re.compile(
    r"429|503|502|504|rate.?limit|too many requests|service unavailable|"
    r"read timed out|connection.?(error|reset|refused)|timeout",
    re.IGNORECASE,
)
MAX_RETRIES = 5


def _is_transient_error(error_msg: str) -> bool:
    return bool(error_msg) and bool(_TRANSIENT_ERROR_PATTERNS.search(str(error_msg)))


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _mark_task(conn, task_id, status, error=None, retry_count=0):
    """
    status='FAILED' + hata GECICI (kota/timeout) + hala deneme hakki varsa:
    gorevi PENDING'e geri dondurup retry_count'u artiriyoruz - boylece bir
    sonraki pipeline calistirmasinda (gunde 3x veya gece) otomatik tekrar
    denenir, elle mudahale gerekmez.
    """
    if status == "FAILED" and _is_transient_error(error) and retry_count < MAX_RETRIES:
        conn.execute(
            "UPDATE content_tasks SET status = 'PENDING', last_error = ?, retry_count = ?, finished_at = ? WHERE id = ?",
            (f"[gecici hata, {retry_count + 1}. deneme sonrasi tekrar kuyruga alindi] {error}", retry_count + 1, _now_iso(), task_id)
        )
    else:
        conn.execute(
            "UPDATE content_tasks SET status = ?, last_error = ?, finished_at = ? WHERE id = ?",
            (status, error, _now_iso(), task_id)
        )
    conn.commit()


def _process_guide_task(task):
    """GUIDE gorevi: bu urun icin 'X ve Alternatifleri' rehberi uretir (quality_gate'den gecerek)."""
    from generate_guide import build_guide_cfg_for_product, run_one
    cfg = build_guide_cfg_for_product(task["product_id"])
    if not cfg:
        return False, "Bu urunun kategorisinde yeterli benzer urun yok (en az 3 arac gerekli)"
    ok, problems = run_one(cfg, validate=True)
    if not ok:
        return False, "; ".join(problems)
    return True, None


def _process_refresh_task(task):
    """REFRESH gorevi: mevcut rehberi ayni konfigurasyonla yeniden uretir (icerigi tazeler)."""
    from generate_guide import build_guide_cfg_for_product, run_one
    from db import get_guides_for_tool_slug
    guides = get_guides_for_tool_slug(task["slug"])
    if not guides:
        return False, "Bu urune bagli rehber bulunamadi (REFRESH icin once GUIDE gerekir)"
    existing_guide = guides[0]
    cfg = build_guide_cfg_for_product(task["product_id"])
    if not cfg:
        return False, "Bu urunun kategorisinde yeterli benzer urun yok"
    # Ayni slug'i koru ki save_guide UPSERT yapip URL'i degistirmesin
    cfg["slug"] = existing_guide["slug"]
    ok, problems = run_one(cfg, validate=True)
    if not ok:
        return False, "; ".join(problems)
    return True, None


# AFFILIATE: bilerek islenmiyor - gercek bir affiliate programina basvurmak/link eklemek
# insan/is karari gerektirir (bkz. onceki oturumlarda affiliate_url'in 0 dolu olmasi tespiti).
# Bu tur gorevler PENDING kalir, admin panelde bir "firsat raporu" olarak gorunmeye devam eder.
_PROCESSORS = {
    "GUIDE": _process_guide_task,
    "REFRESH": _process_refresh_task,
}


def _run_collection_and_comparison_generators(dry_run=False):
    """
    COLLECTION ve COMPARISON, GUIDE/REFRESH'in aksine content_tasks kuyruguna tek tek
    satir olarak girmiyor - cunku generate_collections.py ve auto_generate_comparisons.py
    zaten kendi kendine "uretilecek bir sey var mi" kararini veren, idempotent (var olani
    atlayan) global script'ler. Bu yuzden pipeline onlari her calistiginda dogrudan cagirir;
    ayri bir task satirina zorlamak (product_id NOT NULL join'i icin yapay bir urun secmek
    gerekirdi) gereksiz karmasiklik olurdu. (ChatGPT onerisi degerlendirildi, kullanicinin
    onayiyla bu daha basit yol secildi - 21 Temmuz 2026.)
    """
    if dry_run:
        print("\n[DRY RUN] COLLECTION ve COMPARISON generator'lari calistirilmayacak (sadece gercek modda calisirlar).")
        return
    print("\n--- Koleksiyon ve Karsilastirma Generator'lari ---")
    try:
        import generate_collections
        print("[COLLECTION] generate_collections.run() cagriliyor...")
        generate_collections.run()
    except Exception as e:
        print(f"[COLLECTION] HATA: {e}")
    try:
        import auto_generate_comparisons
        print("[COMPARISON] auto_generate_comparisons.run() cagriliyor...")
        auto_generate_comparisons.run()
    except Exception as e:
        print(f"[COMPARISON] HATA: {e}")


def run_pipeline(dry_run=False, max_tasks=3):
    print("=== Content OS Pipeline Basliyor ===")

    # Puanlari ve firsatlari yenile (Dry run olsa bile firsatlari gormek icin)
    discover_opportunities()

    conn = get_connection()
    tasks = conn.execute("""
        SELECT t.id, t.task_type, t.priority_score, t.reason, t.product_id, t.retry_count, p.original_name, p.slug
        FROM content_tasks t
        JOIN products p ON t.product_id = p.id
        WHERE t.status = 'PENDING'
        ORDER BY t.priority_score DESC
    """).fetchall()
    tasks = [dict(t) for t in tasks]

    if dry_run:
        print("\n--- DRY RUN MODU ---")
        print(f"Toplam Bekleyen Is: {len(tasks)}\n")
        counts = {}
        for t in tasks:
            print(f"[{t['task_type']}] {t['original_name']} (Skor: {t['priority_score']})")
            print(f"  Sebep: {t['reason']}")
            print("-" * 20)
            counts[t["task_type"]] = counts.get(t["task_type"], 0) + 1
        print("\n=== DRY RUN OZET ===")
        for k, v in counts.items():
            print(f"Bekleyen {k}: {v}")
        print("Hicbir islem yapilmadi (Dry Run).")
        conn.close()
        return

    print("\n--- GERCEK CALISMA MODU ---")
    processed = 0
    consecutive_transient_failures = 0
    CIRCUIT_BREAKER_THRESHOLD = 3  # ust uste bu kadar "gecici hata" gorulurse, muhtemelen
    # tum saglayicilar (Groq+Gemini+NVIDIA) ayni anda kota/rate-limit sorunu yasiyor demektir -
    # kalan gorevleri denemeye devam etmek (30 Temmuz 2026'da oldugu gibi 55dk boyunca
    # HEPSI basarisiz olup GitHub'in kendi is zaman asimina takilmak) sadece zaman/kota
    # israf eder. Erken durup kalan gorevleri PENDING birakiyoruz - bir sonraki
    # calistirmada (kota muhtemelen toparlanmisken) otomatik denenecekler.

    for t in tasks:
        processor = _PROCESSORS.get(t["task_type"])
        if not processor:
            continue  # AFFILIATE gibi otomatik islenmeyen tipler atlanir, PENDING kalir
        if processed >= max_tasks:
            print(f"\nBu calistirmada max_tasks={max_tasks} sinirina ulasildi, kalanlar bir sonraki calistirmada islenecek.")
            break
        if consecutive_transient_failures >= CIRCUIT_BREAKER_THRESHOLD:
            print(f"\n!!! DEVRE KESICI: ust uste {CIRCUIT_BREAKER_THRESHOLD} gecici hata (muhtemel tum-saglayici kesintisi). "
                  f"Kalan gorevler PENDING birakilip calistirma erken sonlandiriliyor.")
            break

        print(f"\n[{t['task_type']}] {t['original_name']} isleniyor (skor: {t['priority_score']})...")
        conn.execute("UPDATE content_tasks SET status = 'RUNNING', started_at = ? WHERE id = ?",
                     (_now_iso(), t["id"]))
        conn.commit()
        try:
            ok, error = processor(t)
            _mark_task(conn, t["id"], "SUCCESS" if ok else "FAILED", error, retry_count=t.get("retry_count", 0))
            print(f"  -> {'BASARILI' if ok else 'BASARISIZ: ' + str(error)}")
            if not ok and _is_transient_error(error):
                consecutive_transient_failures += 1
            else:
                consecutive_transient_failures = 0
        except Exception as e:
            _mark_task(conn, t["id"], "FAILED", str(e), retry_count=t.get("retry_count", 0))
            print(f"  -> HATA: {e}")
            if _is_transient_error(str(e)):
                consecutive_transient_failures += 1
            else:
                consecutive_transient_failures = 0
        processed += 1
        time.sleep(8)  # AI saglayicilarinin dakikalik rate-limit'ini zorlamamak icin
        # gorevler arasi kucuk bir bekleme - onceden hic yoktu, art arda gelen
        # istekler Groq/Gemini/NVIDIA'yi ayni anda kotaya takiyordu.

    print(f"\n=== Pipeline bitti. {processed} gorev islendi. ===")

    if consecutive_transient_failures >= CIRCUIT_BREAKER_THRESHOLD:
        print("Devre kesici tetiklendigi icin COLLECTION/COMPARISON generator'lari da bu calistirmada atlaniyor "
              "(muhtemelen ayni saglayici kesintisine carpip vakit kaybederlerdi).")
    else:
        _run_collection_and_comparison_generators(dry_run=dry_run)

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Content OS Automation Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Sadece kuyrugu gosterir, islem yapmaz.")
    parser.add_argument("--max-tasks", type=int, default=3, help="Bu calistirmada islenecek maksimum gorev sayisi.")
    args = parser.parse_args()

    init_db()
    run_pipeline(dry_run=args.dry_run, max_tasks=args.max_tasks)
