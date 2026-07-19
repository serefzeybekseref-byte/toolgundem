"""
Haftalik/anlik saglik raporu: production veritabaninin genel durumunu
tek komutla ozetler.

Kullanim:
    python scripts/maintenance/health_report.py
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dotenv import load_dotenv
load_dotenv()
from db_target import print_db_target
from db import get_connection


def run():
    print_db_target()
    conn = get_connection()

    def scalar(sql):
        row = conn.execute(sql).fetchone()
        return dict(row)[list(dict(row).keys())[0]]

    products = scalar("SELECT COUNT(*) as c FROM products")
    broken = scalar("SELECT COUNT(*) as c FROM products WHERE is_broken=1")
    missing_quickfacts = scalar(
        "SELECT COUNT(*) as c FROM products WHERE platforms IS NULL OR platforms='' "
        "OR pricing_type IS NULL OR pricing_type='' OR key_features IS NULL OR key_features=''"
    )
    avg_quality = scalar("SELECT AVG(quality_score) as c FROM products")

    try:
        guides = scalar("SELECT COUNT(*) as c FROM guides")
    except Exception:
        guides = "N/A"

    try:
        comparisons = scalar("SELECT COUNT(*) as c FROM comparisons")
    except Exception:
        comparisons = "N/A"

    try:
        collections = scalar("SELECT COUNT(*) as c FROM collections")
    except Exception:
        collections = "N/A"

    conn.close()

    print()
    print(f"Rapor tarihi     : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Products         : {products}")
    print(f"Broken links     : {broken}")
    print(f"Missing quickfacts: {missing_quickfacts}")
    print(f"Average quality  : {avg_quality:.1f}" if avg_quality else "Average quality  : N/A")
    print(f"Guides           : {guides}")
    print(f"Comparisons      : {comparisons}")
    print(f"Collections      : {collections}")


if __name__ == "__main__":
    run()
