"""
Veritabani katmani.
DATABASE_URL ortam degiskeni tanimliysa PostgreSQL (Supabase/Neon vb.) kullanilir,
tanimli degilse yerel SQLite (products.db) kullanilir.
Bu sayede kod hem lokal gelistirmede hem de Vercel gibi kalici disk sunmayan
serverless ortamlarda calisabilir hale gelir.
"""
import os
import re
import logging
import sqlite3
import unicodedata
from datetime import datetime

logger = logging.getLogger("toolgundem.db")

DB_PATH = "products.db"
DATABASE_URL = os.environ.get("DATABASE_URL")
USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras


def _pg_sql(sql: str) -> str:
    """SQLite tarzi '?' placeholder'lari Postgres'in '%s' formatina cevirir."""
    return sql.replace("?", "%s")

class _PGCursorWrapper:
    """psycopg2 cursor'unu sqlite3.Cursor ile ayni arayuze (fetchone/fetchall/lastrowid) sarar."""

    def __init__(self, cursor):
        self._cursor = cursor
        self._cached_row = None
        self._cached = False

    def fetchone(self):
        if self._cached:
            self._cached = False
            return self._cached_row
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def lastrowid(self):
        """INSERT ... RETURNING id ile eslesen satiri lastrowid gibi dondurur."""
        try:
            row = self._cursor.fetchone()
            self._cached_row = row
            self._cached = True
            return row["id"] if row else None
        except Exception:
            return None


class _ConnWrapper:
    """SQLite ve Postgres baglantilarini tek bir arayuz (execute/commit/close) altinda birlestirir."""

    def __init__(self, raw, is_pg):
        self.raw = raw
        self.is_pg = is_pg

    def execute(self, sql, params=()):
        if self.is_pg:
            cur = self.raw.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            converted = _pg_sql(sql)
            stripped = converted.strip().upper()
            if stripped.startswith("INSERT") and "RETURNING" not in stripped:
                converted += " RETURNING id"
            cur.execute(converted, params)
            return _PGCursorWrapper(cur)
        return self.raw.execute(sql, params)

    def commit(self):
        self.raw.commit()

    def close(self):
        self.raw.close()


def get_connection():
    if USE_POSTGRES:
        raw = psycopg2.connect(DATABASE_URL)
        return _ConnWrapper(raw, is_pg=True)
    raw = sqlite3.connect(DB_PATH)
    raw.row_factory = sqlite3.Row
    return _ConnWrapper(raw, is_pg=False)


def init_db():
    conn = get_connection()
    pk = "SERIAL PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"

    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS products (
            id {pk},
            ph_id TEXT UNIQUE NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            original_name TEXT,
            title_tr TEXT,
            summary_tr TEXT,
            content_tr TEXT,
            tags TEXT,
            ph_url TEXT,
            website TEXT,
            thumbnail TEXT,
            votes INTEGER,
            topics TEXT,
            created_at TEXT
        )
    """)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS comparisons (
            id {pk},
            slug TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            intro TEXT,
            updated_at TEXT
        )
    """)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS collections (
            id {pk},
            slug TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            cover_image TEXT,
            created_at TEXT
        )
    """)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS collection_items (
            id {pk},
            collection_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            order_num INTEGER DEFAULT 0,
            reason TEXT,
            FOREIGN KEY (collection_id) REFERENCES collections (id),
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
    """)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS comparison_items (
            id {pk},
            comparison_id INTEGER NOT NULL,
            rank INTEGER NOT NULL,
            name TEXT NOT NULL,
            score REAL NOT NULL,
            pricing TEXT,
            best_for TEXT,
            pros TEXT,
            cons TEXT,
            website TEXT,
            FOREIGN KEY (comparison_id) REFERENCES comparisons (id)
        )
    """)

    # Yeni kolonlar: veri modelini genisletir (duplicate kontrolu, filtreleme,
    # affiliate ve broken-link takibi icin). Zaten varsa hatasiz gecilir.
    new_columns = [
        ("why_use_it", "TEXT"),
        ("key_features", "TEXT"),
        ("normalized_name", "TEXT"),
        ("platforms", "TEXT"),
        ("pricing_type", "TEXT"),
        ("affiliate_url", "TEXT"),
        ("is_partner", "INTEGER DEFAULT 0"),
        ("last_checked_at", "TEXT"),
        ("is_broken", "INTEGER DEFAULT 0"),
    ]
    for col_name, col_type in new_columns:
        if USE_POSTGRES:
            conn.execute(f"ALTER TABLE products ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
        else:
            try:
                conn.execute(f"ALTER TABLE products ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                pass

    conn.commit()
    conn.close()

def slugify(text: str) -> str:
    """Turkce karakterleri temizleyip URL-dostu slug uretir."""
    text = text.replace("ı", "i").replace("İ", "i").replace("ğ", "g").replace("Ğ", "g")
    text = text.replace("ü", "u").replace("Ü", "u").replace("ş", "s").replace("Ş", "s")
    text = text.replace("ö", "o").replace("Ö", "o").replace("ç", "c").replace("Ç", "c")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text


def normalize_name(name: str) -> str:
    """
    Duplicate tespiti icin urun adini sadelestirir:
    kucuk harf, aksansiz, yaygin ek kelimeler ("AI", "app" vb.) temizlenmis hali.
    Ornek: "Claude AI" ve "Claude" ayni normalized_name'e duser -> "claude"
    """
    if not name:
        return ""
    n = name.lower().strip()
    n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode("ascii")
    n = re.sub(r"[^a-z0-9]+", " ", n).strip()
    n = re.sub(r"\b(ai|app|io|the|inc|by|official)\b", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def find_possible_duplicate(name: str, website: str = ""):
    """
    Yeni eklenecek urunun veritabaninda zaten var olup olmadigini,
    sadece ph_id degil isim/website benzerligiyle de kontrol eder.
    ph_id farkli olsa bile (farkli kaynak, yeniden submit vb.) ayni araci yakalamayi amaclar.
    """
    conn = get_connection()
    norm = normalize_name(name)
    row = None
    if norm:
        row = conn.execute(
            "SELECT * FROM products WHERE normalized_name = ?", (norm,)
        ).fetchone()
    if not row and website:
        domain = website.lower().strip().rstrip("/")
        domain = re.sub(r"^https?://(www\.)?", "", domain)
        if domain:
            row = conn.execute(
                "SELECT * FROM products WHERE website LIKE ?", (f"%{domain}%",)
            ).fetchone()
    conn.close()
    return dict(row) if row else None


def product_exists(ph_id: str) -> bool:
    conn = get_connection()
    row = conn.execute("SELECT 1 FROM products WHERE ph_id = ?", (ph_id,)).fetchone()
    conn.close()
    return row is not None


def save_product(product: dict, ai_content: dict) -> str:
    """
    product: fetch_producthunt'tan gelen ham urun dict'i
    ai_content: generate_content'ten gelen {"title","summary","content","tags"}
    Donen: slug (detay sayfasi icin)
    """
    base_slug = slugify(ai_content["title"])
    slug = base_slug
    conn = get_connection()

    counter = 2
    while conn.execute("SELECT 1 FROM products WHERE slug = ?", (slug,)).fetchone():
        slug = f"{base_slug}-{counter}"
        counter += 1

    normalized = normalize_name(product.get("name") or ai_content["title"])

    conn.execute("""
        INSERT INTO products
        (ph_id, slug, original_name, title_tr, summary_tr, content_tr, tags,
         ph_url, website, thumbnail, votes, topics, created_at, normalized_name)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        product["id"], slug, product["name"],
        ai_content["title"], ai_content["summary"], ai_content["content"],
        ",".join(ai_content["tags"]),
        product["url"], product.get("website", ""), product.get("thumbnail"),
        product["votes"], ",".join(product.get("topics", [])),
        datetime.utcnow().isoformat(), normalized,
    ))
    conn.commit()
    conn.close()
    return slug

def get_all_products():
    """Tum urunleri en yeniden en eskiye siralar."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM products ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_product_by_slug(slug: str):
    conn = get_connection()
    row = conn.execute("SELECT * FROM products WHERE slug = ?", (slug,)).fetchone()
    conn.close()
    return dict(row) if row else None


def save_comparison(slug: str, title: str, intro: str, items: list):
    """
    items: [{"rank":1,"name":..,"score":9.4,"pricing":..,"best_for":..,
             "pros":[...],"cons":[...],"website":..}, ...]
    Ayni slug varsa once eski kayitlar silinip yenisi yazilir (guncelleme).
    """
    conn = get_connection()
    existing = conn.execute("SELECT id FROM comparisons WHERE slug = ?", (slug,)).fetchone()
    if existing:
        comparison_id = dict(existing)["id"]
        conn.execute("UPDATE comparisons SET title=?, intro=?, updated_at=? WHERE id=?",
                     (title, intro, datetime.utcnow().isoformat(), comparison_id))
        conn.execute("DELETE FROM comparison_items WHERE comparison_id=?", (comparison_id,))
    else:
        cur = conn.execute(
            "INSERT INTO comparisons (slug, title, intro, updated_at) VALUES (?, ?, ?, ?)",
            (slug, title, intro, datetime.utcnow().isoformat())
        )
        comparison_id = cur.lastrowid

    for item in items:
        conn.execute("""
            INSERT INTO comparison_items
            (comparison_id, rank, name, score, pricing, best_for, pros, cons, website)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            comparison_id, item["rank"], item["name"], item["score"],
            item.get("pricing", ""), item.get("best_for", ""),
            "|".join(item.get("pros", [])), "|".join(item.get("cons", [])),
            item.get("website", ""),
        ))
    conn.commit()
    conn.close()
    return comparison_id


def get_all_comparisons():
    conn = get_connection()
    rows = conn.execute("""
        SELECT c.*, COUNT(ci.id) AS tool_count
        FROM comparisons c
        LEFT JOIN comparison_items ci ON ci.comparison_id = c.id
        GROUP BY c.id
        ORDER BY c.updated_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_comparison_by_slug(slug: str):
    conn = get_connection()
    comp = conn.execute("SELECT * FROM comparisons WHERE slug = ?", (slug,)).fetchone()
    if not comp:
        conn.close()
        return None
    comp = dict(comp)
    items = conn.execute(
        "SELECT * FROM comparison_items WHERE comparison_id = ? ORDER BY rank ASC",
        (comp["id"],)
    ).fetchall()
    conn.close()
    comp["tools"] = []
    for it in items:
        it = dict(it)
        it["pros"] = it["pros"].split("|") if it["pros"] else []
        it["cons"] = it["cons"].split("|") if it["cons"] else []
        comp["tools"].append(it)
    return comp

def get_trending_products(limit=5):
    """En cok oy alan urunler."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM products ORDER BY votes DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_products(limit=10):
    """Son eklenen urunler."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM products ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_products_by_topic(topic, limit=50):
    """Belirli bir kategorideki urunler."""
    conn = get_connection()
    pattern = f"%{topic}%"
    rows = conn.execute("SELECT * FROM products WHERE topics LIKE ? ORDER BY votes DESC LIMIT ?", (pattern, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_products(query):
    """Baslik veya ozette arama."""
    conn = get_connection()
    pattern = f"%{query}%"
    rows = conn.execute(
        "SELECT * FROM products WHERE title_tr LIKE ? OR summary_tr LIKE ? OR original_name LIKE ? ORDER BY votes DESC",
        (pattern, pattern, pattern)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_topics():
    """Tum benzersiz kategorileri dondurur."""
    conn = get_connection()
    rows = conn.execute("SELECT topics FROM products WHERE topics IS NOT NULL AND topics != ''").fetchall()
    conn.close()
    topic_count = {}
    for row in rows:
        for t in dict(row)["topics"].split(","):
            t = t.strip()
            if t:
                topic_count[t] = topic_count.get(t, 0) + 1
    sorted_topics = sorted(topic_count.items(), key=lambda x: x[1], reverse=True)
    return sorted_topics


def get_similar_products(product_id, limit=4):
    """Ayni topic'teki diger urunler."""
    conn = get_connection()
    product = conn.execute("SELECT topics FROM products WHERE id = ?", (product_id,)).fetchone()
    if not product or not dict(product).get("topics"):
        conn.close()
        return []
    topics = dict(product)["topics"].split(",")
    if not topics:
        conn.close()
        return []
    first_topic = topics[0].strip()
    rows = conn.execute(
        "SELECT * FROM products WHERE topics LIKE ? AND id != ? ORDER BY votes DESC LIMIT ?",
        (f"%{first_topic}%", product_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_products_paginated(page=1, per_page=20):
    """Sayfalanmis urun listesi."""
    conn = get_connection()
    offset = (page - 1) * per_page
    rows = conn.execute("SELECT * FROM products ORDER BY votes DESC LIMIT ? OFFSET ?", (per_page, offset)).fetchall()
    total = conn.execute("SELECT COUNT(*) as cnt FROM products").fetchone()
    conn.close()
    return [dict(r) for r in rows], dict(total)["cnt"]


def get_all_collections():
    """Tum koleksiyonlari dondurur."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM collections ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_collection_by_slug(slug):
    """Slug ile tek bir koleksiyonu ve icindeki urunleri dondurur."""
    conn = get_connection()
    col = conn.execute("SELECT * FROM collections WHERE slug = ?", (slug,)).fetchone()
    if not col:
        conn.close()
        return None
    col = dict(col)

    items = conn.execute("""
        SELECT p.*, ci.reason
        FROM collection_items ci
        JOIN products p ON p.id = ci.product_id
        WHERE ci.collection_id = ?
        ORDER BY ci.order_num ASC
    """, (col["id"],)).fetchall()

    col["items"] = [dict(r) for r in items]
    conn.close()
    return col


def mark_link_checked(product_id: int, is_broken: bool):
    """Broken-link kontrol scripti tarafindan kullanilir (bkz. check_links.py)."""
    conn = get_connection()
    conn.execute(
        "UPDATE products SET last_checked_at = ?, is_broken = ? WHERE id = ?",
        (datetime.utcnow().isoformat(), 1 if is_broken else 0, product_id)
    )
    conn.commit()
    conn.close()
