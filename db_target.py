"""
Kucuk ortak yardimci: script'lerin hangi veritabanina bagli oldugunu
net bicimde ekrana yazdirir ve local SQLite'a yanlislikla mutating
backfill calistirmayi engeller.

Kullanim (her script'in basinda):

    from dotenv import load_dotenv
    load_dotenv()
    from db_target import print_db_target, guard_postgres
    print_db_target()
    guard_postgres()   # sadece veritabanini DEGISTIREN script'lerde cagir
"""
import os
import sys
import re


def _target_info():
    url = os.environ.get("DATABASE_URL")
    if url:
        # host'u guvenli sekilde cikar (sifreyi loglama)
        m = re.search(r"@([^/:]+)", url)
        host = m.group(1) if m else "?"
        return True, host
    return False, None


def print_db_target():
    is_pg, host = _target_info()
    print("=" * 50)
    if is_pg:
        print("Database : PostgreSQL (Supabase)")
        print(f"Host     : {host}")
        print("Mode     : PRODUCTION")
    else:
        print("Database : SQLite")
        print("File     : products.db")
        print("Mode     : LOCAL (production'a yazilmiyor!)")
    print("=" * 50)


def guard_postgres():
    """Mutating backfill script'leri icin: --allow-sqlite verilmedikce
    Postgres disinda calismayi reddeder."""
    is_pg, _ = _target_info()
    if not is_pg and "--allow-sqlite" not in sys.argv:
        print("Refusing to modify local SQLite.")
        print("Run again with --allow-sqlite if this is intentional (local test).")
        sys.exit(1)
