import sys
import argparse
from datetime import datetime
from db import get_connection, init_db
from content_intelligence import discover_opportunities

def run_pipeline(dry_run=False):
    print("=== Lean Content OS Pipeline Basliyor ===")
    
    # Puanlari ve firsatlari yenile (Dry run olsa bile firsatlari gormek icin)
    discover_opportunities()
    
    conn = get_connection()
    tasks = conn.execute("""
        SELECT t.id, t.task_type, t.priority_score, t.reason, t.estimated_cost, p.original_name, p.slug
        FROM content_tasks t
        JOIN products p ON t.product_id = p.id
        WHERE t.status = 'PENDING'
        ORDER BY t.priority_score DESC
    """).fetchall()
    
    if dry_run:
        print("\n--- DRY RUN MODU ---")
        print(f"Toplam Bekleyen Is: {len(tasks)}\n")
        
        total_cost = 0.0
        counts = {"GUIDE": 0, "COMPARISON": 0, "COLLECTION": 0, "AFFILIATE": 0, "REFRESH": 0}
        
        for t in tasks:
            print(f"[{t['task_type']}] {t['original_name']} (Skor: {t['priority_score']})")
            print(f"  Sebep: {t['reason']}")
            cost = t['estimated_cost'] or 0.0
            total_cost += cost
            if cost > 0:
                print(f"  Tahmini Maliyet: ${cost:.2f}")
            print("-" * 20)
            
            if t['task_type'] in counts:
                counts[t['task_type']] += 1
                
        print("\n=== DRY RUN OZET ===")
        for k, v in counts.items():
            if v > 0:
                print(f"Uretilecek {k}: {v}")
        print(f"Toplam Beklenen Maliyet: ${total_cost:.2f}")
        print("Hicbir islem yapilmadi (Dry Run).")
    else:
        print("\n--- GERCEK CALISMA MODU ---")
        # Ileride: Gercek uretim modulleri (generate_guide.py vb.) burada cagrilacak.
        # Bu sprintte altyapiyi kurduk, bilesenleri cagirarak PENDING gorevleri isleyebiliriz.
        print("Gorevler sirasiyla isleniyor (Simulasyon)...")
        # Her islem bittiginde status SUCCESS/FAILED yapilip, pipeline_runs tablosuna log atilacak.

    conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Content OS Automation Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Sadece kuyrugu ve maliyeti gosterir, islem yapmaz.")
    args = parser.parse_args()
    
    init_db()
    run_pipeline(dry_run=args.dry_run)
