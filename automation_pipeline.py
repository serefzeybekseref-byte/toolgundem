import sys
import argparse
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()
from db import get_connection, init_db
from content_intelligence import discover_opportunities


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _mark_task(conn, task_id, status, error=None):
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


def run_pipeline(dry_run=False, max_tasks=3):
    print("=== Content OS Pipeline Basliyor ===")

    # Puanlari ve firsatlari yenile (Dry run olsa bile firsatlari gormek icin)
    discover_opportunities()

    conn = get_connection()
    tasks = conn.execute("""
        SELECT t.id, t.task_type, t.priority_score, t.reason, t.product_id, p.original_name, p.slug
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
    for t in tasks:
        processor = _PROCESSORS.get(t["task_type"])
        if not processor:
            continue  # AFFILIATE gibi otomatik islenmeyen tipler atlanir, PENDING kalir
        if processed >= max_tasks:
            print(f"\nBu calistirmada max_tasks={max_tasks} sinirina ulasildi, kalanlar bir sonraki calistirmada islenecek.")
            break

        print(f"\n[{t['task_type']}] {t['original_name']} isleniyor (skor: {t['priority_score']})...")
        conn.execute("UPDATE content_tasks SET status = 'RUNNING', started_at = ? WHERE id = ?",
                     (_now_iso(), t["id"]))
        conn.commit()
        try:
            ok, error = processor(t)
            _mark_task(conn, t["id"], "SUCCESS" if ok else "FAILED", error)
            print(f"  -> {'BASARILI' if ok else 'BASARISIZ: ' + str(error)}")
        except Exception as e:
            _mark_task(conn, t["id"], "FAILED", str(e))
            print(f"  -> HATA: {e}")
        processed += 1

    print(f"\n=== Pipeline bitti. {processed} gorev islendi. ===")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Content OS Automation Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Sadece kuyrugu gosterir, islem yapmaz.")
    parser.add_argument("--max-tasks", type=int, default=3, help="Bu calistirmada islenecek maksimum gorev sayisi.")
    args = parser.parse_args()

    init_db()
    run_pipeline(dry_run=args.dry_run, max_tasks=args.max_tasks)
