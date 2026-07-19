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
from datetime import datetime, timedelta

logger = logging.getLogger("toolgundem.db")

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "products.db")
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


try:
    from flask import g, has_request_context
except ImportError:
    g = None
    def has_request_context():
        return False


class _ConnWrapper:
    """SQLite ve Postgres baglantilarini tek bir arayuz (execute/commit/close) altinda birlestirir."""

    def __init__(self, raw, is_pg, shared=False):
        self.raw = raw
        self.is_pg = is_pg
        self.shared = shared

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
        # Istek-basi paylasilan baglantilar tek tek kapatilmaz;
        # gercek kapama Flask'in teardown_appcontext'inde yapilir.
        if not self.shared:
            self.raw.close()


def _open_raw_connection(shared):
    if USE_POSTGRES:
        raw = psycopg2.connect(DATABASE_URL)
        return _ConnWrapper(raw, is_pg=True, shared=shared)
    raw = sqlite3.connect(DB_PATH)
    raw.row_factory = sqlite3.Row
    return _ConnWrapper(raw, is_pg=False, shared=shared)


def get_connection():
    """
    Flask istek baglaminda (web istekleri) tek bir baglanti acilip istek
    boyunca paylasilir - boylece bir sayfa yuklemesinde 7-8 ayri Supabase
    SSL handshake'i yerine sadece 1 tane acilir (onceden ~6sn suren ana
    sayfa yuklemesi bu sekilde hizlanir). Istek disi (pipeline/script)
    kullanimda eskisi gibi her cagrida yeni baglanti acilir.
    """
    if has_request_context():
        if not hasattr(g, "_db_conn"):
            g._db_conn = _open_raw_connection(shared=True)
        return g._db_conn
    return _open_raw_connection(shared=False)


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
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id {pk},
            ran_at TEXT,
            new_count INTEGER,
            error_count INTEGER
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
        CREATE TABLE IF NOT EXISTS subscribers (
            id {pk},
            email TEXT UNIQUE NOT NULL,
            subscribed_at TEXT,
            is_active INTEGER DEFAULT 1
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
        ("quality_score", "INTEGER DEFAULT 0"),
        ("gallery", "TEXT"),
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

def compute_quality_score(row: dict) -> int:
    """
    Deterministik tamlik puani (0-100). LLM'e "kaliteli mi?" diye SORMAZ -
    sadece hangi alanlarin dolu/yeterli oldugunu sayar. Ayni girdi her zaman
    ayni puanu verir, bu yuzden editor panelinde ve kullanicida guvenilir bir
    sinyal olarak kullanilabilir.
    Agirliklar: description/summary 25, platform 10, fiyat 10, key_features>=3 15,
    alternatif/topic 15, son kontrol edilmis 10, logo 5, website 10.
    """
    score = 0
    if (row.get("summary_tr") or "").strip():
        score += 15
    if (row.get("content_tr") or "").strip():
        score += 10
    if (row.get("platforms") or "").strip():
        score += 10
    if (row.get("pricing_type") or "").strip() and row.get("pricing_type") != "Bilinmiyor":
        score += 10
    features = row.get("key_features") or ""
    if isinstance(features, list):
        feature_count = len(features)
    else:
        feature_count = len([f for f in features.split(",") if f.strip()])
    if feature_count >= 3:
        score += 15
    elif feature_count > 0:
        score += 7
    if (row.get("topics") or "").strip():
        score += 15
    if (row.get("last_checked_at") or "").strip() and not row.get("is_broken"):
        score += 10
    if (row.get("thumbnail") or "").strip():
        score += 5
    if (row.get("website") or "").strip():
        score += 10
    return min(score, 100)


def update_quality_score(product_id: int, row: dict = None):
    """Bir urunun quality_score'unu (yeniden) hesaplayip kaydeder."""
    conn = get_connection()
    if row is None:
        existing = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        if not existing:
            conn.close()
            return None
        row = dict(existing)
    score = compute_quality_score(row)
    conn.execute("UPDATE products SET quality_score = ? WHERE id = ?", (score, product_id))
    conn.commit()
    conn.close()
    return score


def recompute_all_quality_scores():
    """Tum urunler icin quality_score'u yeniden hesaplar (backfill / bakim scripti icin)."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM products").fetchall()
    conn.close()
    updated = 0
    for r in rows:
        row = dict(r)
        update_quality_score(row["id"], row)
        updated += 1
    return updated


def log_pipeline_run(new_count: int, error_count: int = 0):
    """Her pipeline calistirmasinin ozetini kaydeder (saglik izleme icin)."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO pipeline_runs (ran_at, new_count, error_count) VALUES (?, ?, ?)",
        (datetime.utcnow().isoformat(), new_count, error_count)
    )
    conn.commit()
    conn.close()


def should_alert_zero_new() -> bool:
    """
    Son 2 calistirmada da (farkli takvim gununde) 0 yeni urun eklenmisse True doner.
    Ayni gun icindeki normal (bos gecebilen) calistirmalari yanlis alarm olarak saymamak
    icin farkli gun kontrolu yapilir.
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT ran_at, new_count FROM pipeline_runs ORDER BY id DESC LIMIT 6"
    ).fetchall()
    conn.close()
    rows = [dict(r) for r in rows]
    if len(rows) < 2:
        return False
    zero_days = set()
    for r in rows:
        if r["new_count"] == 0:
            zero_days.add(r["ran_at"][:10])
        else:
            break  # en sonuncudan geriye dogru ilk >0 bulunca dur
    return len(zero_days) >= 2


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
         ph_url, website, thumbnail, votes, topics, created_at, normalized_name,
         why_use_it, key_features, platforms, pricing_type, quality_score, gallery)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        product["id"], slug, product["name"],
        ai_content["title"], ai_content["summary"], ai_content["content"],
        ",".join(ai_content["tags"]),
        product["url"], product.get("website", ""), product.get("thumbnail"),
        product["votes"], ",".join(product.get("topics", [])),
        datetime.utcnow().isoformat(), normalized,
        ai_content.get("why_use_it", ""),
        ",".join(ai_content.get("key_features", [])) if isinstance(ai_content.get("key_features"), list) else ai_content.get("key_features", ""),
        ai_content.get("platforms", ""),
        ai_content.get("pricing_type", ""),
        compute_quality_score({
            "summary_tr": ai_content["summary"],
            "content_tr": ai_content["content"],
            "platforms": ai_content.get("platforms", ""),
            "pricing_type": ai_content.get("pricing_type", ""),
            "key_features": ai_content.get("key_features", ""),
            "topics": ",".join(product.get("topics", [])),
            "last_checked_at": "",
            "is_broken": 0,
            "thumbnail": product.get("thumbnail"),
            "website": product.get("website", ""),
        }),
        ",".join(product.get("gallery", [])),
    ))
    conn.commit()
    conn.close()
    return slug

def get_products_missing_quickfacts(limit: int = 20):
    """why_use_it alani bos olan urunleri dondurur (backfill icin)."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM products
        WHERE why_use_it IS NULL OR why_use_it = ''
        ORDER BY votes DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_product_quickfacts(product_id, why_use_it, key_features, platforms, pricing_type):
    """Var olan bir urunun why_use_it/key_features/platforms/pricing_type alanlarini gunceller."""
    conn = get_connection()
    conn.execute("""
        UPDATE products
        SET why_use_it = ?, key_features = ?, platforms = ?, pricing_type = ?
        WHERE id = ?
    """, (why_use_it, key_features, platforms, pricing_type, product_id))
    conn.commit()
    conn.close()


def get_admin_stats():
    """Admin paneli icin ozet istatistikler (tek sorgu setiyle)."""
    conn = get_connection()

    total_products = dict(conn.execute("SELECT COUNT(*) as c FROM products").fetchone())["c"]
    avg_quality = conn.execute("SELECT AVG(quality_score) as a FROM products").fetchone()
    avg_quality = round(dict(avg_quality)["a"] or 0, 1)

    quality_buckets = conn.execute("""
        SELECT
            SUM(CASE WHEN quality_score >= 80 THEN 1 ELSE 0 END) as yuksek,
            SUM(CASE WHEN quality_score >= 50 AND quality_score < 80 THEN 1 ELSE 0 END) as orta,
            SUM(CASE WHEN quality_score < 50 THEN 1 ELSE 0 END) as dusuk
        FROM products
    """).fetchone()
    quality_buckets = dict(quality_buckets)

    broken_links = dict(conn.execute("SELECT COUNT(*) as c FROM products WHERE is_broken = 1").fetchone())["c"]
    never_checked = dict(conn.execute(
        "SELECT COUNT(*) as c FROM products WHERE last_checked_at IS NULL OR last_checked_at = ''"
    ).fetchone())["c"]

    total_comparisons = dict(conn.execute("SELECT COUNT(*) as c FROM comparisons").fetchone())["c"]
    total_collections = dict(conn.execute("SELECT COUNT(*) as c FROM collections").fetchone())["c"]

    top_topics = conn.execute("""
        SELECT topics FROM products WHERE topics IS NOT NULL AND topics != ''
    """).fetchall()
    from collections import Counter
    topic_counter = Counter()
    for row in top_topics:
        for t in dict(row)["topics"].split(","):
            t = t.strip()
            if t:
                topic_counter[t] += 1
    top_topics_list = topic_counter.most_common(10)

    recent = conn.execute(
        "SELECT original_name, slug, quality_score, created_at FROM products ORDER BY created_at DESC LIMIT 10"
    ).fetchall()
    recent = [dict(r) for r in recent]

    pricing_breakdown = conn.execute("""
        SELECT pricing_type, COUNT(*) as c FROM products
        WHERE pricing_type IS NOT NULL AND pricing_type != ''
        GROUP BY pricing_type ORDER BY c DESC
    """).fetchall()
    pricing_breakdown = [dict(r) for r in pricing_breakdown]

    conn.close()
    return {
        "total_products": total_products,
        "avg_quality": avg_quality,
        "quality_buckets": quality_buckets,
        "broken_links": broken_links,
        "never_checked": never_checked,
        "total_comparisons": total_comparisons,
        "total_collections": total_collections,
        "top_topics": top_topics_list,
        "recent": recent,
        "pricing_breakdown": pricing_breakdown,
    }


def get_all_products():
    """Tum urunleri en yeniden en eskiye siralar (ornegin sitemap.xml icin -
    kirik link isaretli urunler haric, boylece Google olu sayfalari indexlemez)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM products WHERE (is_broken IS NULL OR is_broken = 0) ORDER BY created_at DESC"
    ).fetchall()
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
    comp["tools"] = []
    for it in items:
        it = dict(it)
        it["pros"] = it["pros"].split("|") if it["pros"] else []
        it["cons"] = it["cons"].split("|") if it["cons"] else []
        # Ic sayfa cross-link: bu urunumuzde varsa slug'ini bul (normalized_name eslesmesi)
        norm = normalize_name(it["name"])
        match = conn.execute(
            "SELECT slug, is_broken FROM products WHERE normalized_name = ?", (norm,)
        ).fetchone()
        match = dict(match) if match else None
        # Eslesen urun kendi kataloğumuzda kirik isaretliyse, bu karsilastirmada gosterilmez
        # (comparison_items ayri/bagimsiz bir tablo oldugu icin websitesi kendi basina
        # kontrol edilmiyor - sadece katalogda eslesen urunler icin bu koruma calisir).
        if match and match.get("is_broken"):
            continue
        it["internal_slug"] = match["slug"] if match else None
        comp["tools"].append(it)
    conn.close()
    return comp


def get_comparisons_for_product(normalized_name: str, limit: int = 3):
    """Bir urunun adi hangi karsilastirma sayfalarinda geciyorsa onlari dondurur (cross-link icin)."""
    if not normalized_name:
        return []
    conn = get_connection()
    rows = conn.execute("""
        SELECT DISTINCT c.slug, c.title
        FROM comparisons c
        JOIN comparison_items ci ON ci.comparison_id = c.id
        WHERE LOWER(REPLACE(ci.name, ' ', '')) LIKE ?
        LIMIT ?
    """, (f"%{normalized_name.replace(' ', '')}%", limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_collections_for_product(product_id: int, limit: int = 3):
    """Bir urunun hangi koleksiyonlarda yer aldigini dondurur (cross-link icin)."""
    if not product_id:
        return []
    conn = get_connection()
    rows = conn.execute("""
        SELECT DISTINCT col.slug, col.title
        FROM collections col
        JOIN collection_items ci ON ci.collection_id = col.id
        WHERE ci.product_id = ?
        LIMIT ?
    """, (product_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_trending_products(limit=5):
    """En cok oy alan urunler. Kirik link isaretli urunler kesif yuzeylerinde gosterilmez."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM products WHERE (is_broken IS NULL OR is_broken = 0) ORDER BY votes DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_products(limit=10):
    """Son eklenen urunler. Kirik link isaretli urunler kesif yuzeylerinde gosterilmez."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM products WHERE (is_broken IS NULL OR is_broken = 0) ORDER BY created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def subscribe_email(email: str) -> str:
    """
    Bulten aboneligi kaydeder. Zaten kayitliysa (UNIQUE ihlali) sessizce basarili sayar
    (kullaniciya "zaten abonesin" hissi vermek yerine ayni "tesekkurler" mesajini gosterebilmek icin).
    Donen: "yeni" | "zaten_var" | "gecersiz"
    """
    email = (email or "").strip().lower()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return "gecersiz"
    conn = get_connection()
    existing = conn.execute("SELECT is_active FROM subscribers WHERE email = ?", (email,)).fetchone()
    if existing:
        if dict(existing)["is_active"]:
            conn.close()
            return "zaten_var"
        # Daha once abonelikten cikmis - tekrar aktiflestir (yeni satir eklemeye gerek yok)
        conn.execute("UPDATE subscribers SET is_active = 1, subscribed_at = ? WHERE email = ?",
                     (datetime.utcnow().isoformat(), email))
        conn.commit()
        conn.close()
        return "yeni"
    conn.execute(
        "INSERT INTO subscribers (email, subscribed_at, is_active) VALUES (?, ?, 1)",
        (email, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()
    return "yeni"


def get_active_subscribers():
    """Haftalik bulten gonderimi icin aktif abone listesini dondurur."""
    conn = get_connection()
    rows = conn.execute("SELECT email FROM subscribers WHERE is_active = 1").fetchall()
    conn.close()
    return [dict(r)["email"] for r in rows]


def unsubscribe_email(email: str) -> bool:
    """Abonelikten cikar (is_active=0). Kaydi silmez, gecmis icin tutar."""
    email = (email or "").strip().lower()
    conn = get_connection()
    conn.execute("UPDATE subscribers SET is_active = 0 WHERE email = ?", (email,))
    conn.commit()
    conn.close()
    return True


def get_top_products_by_period(days: int, limit: int = 10, exclude_ids=None):
    """
    Son N gun icinde eklenen urunleri oy sayisina gore siralar (Product Hunt'in
    "Dun/Bu Hafta/Bu Ay En Iyileri" tarzi bolumleri icin). Yeni AI uretimi
    gerektirmez - mevcut votes + created_at verisiyle calisir.
    days=1 -> son 24 saat, days=7 -> son hafta, days=30 -> son ay.
    exclude_ids: bu id'lere sahip urunler sonuca dahil edilmez (ornegin
    "Bu Ayin En Iyileri" bolumunde "Bu Haftanin En Iyileri"nde zaten
    gosterilen urunlerin tekrar etmemesi icin kullanilir).
    """
    conn = get_connection()
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    exclude_ids = exclude_ids or []
    if exclude_ids:
        placeholders = ",".join("?" * len(exclude_ids))
        rows = conn.execute(
            f"SELECT * FROM products WHERE created_at >= ? AND id NOT IN ({placeholders}) AND (is_broken IS NULL OR is_broken = 0) ORDER BY votes DESC LIMIT ?",
            (cutoff, *exclude_ids, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM products WHERE created_at >= ? AND (is_broken IS NULL OR is_broken = 0) ORDER BY votes DESC LIMIT ?",
            (cutoff, limit)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_products_by_topic(topic, limit=50):
    """Belirli bir kategorideki urunler. Kirik link isaretli urunler gosterilmez."""
    conn = get_connection()
    pattern = f"%{topic}%"
    rows = conn.execute(
        "SELECT * FROM products WHERE topics LIKE ? AND (is_broken IS NULL OR is_broken = 0) ORDER BY votes DESC LIMIT ?",
        (pattern, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_products(query):
    """Baslik veya ozette arama (site ici klasik arama kutusu icin - literal alt-dize).
    Buyuk/kucuk harf duyarsiz (Postgres LIKE varsayilan olarak duyarli, SQLite duyarsiz -
    farkli davranmalarini onlemek icin ikisinde de LOWER() ile normalize ediyoruz).
    Kirik link isaretli urunler sonuclara dahil edilmez."""
    conn = get_connection()
    pattern = f"%{query.lower()}%"
    rows = conn.execute(
        "SELECT * FROM products WHERE (LOWER(title_tr) LIKE ? OR LOWER(summary_tr) LIKE ? OR LOWER(original_name) LIKE ?) AND (is_broken IS NULL OR is_broken = 0) ORDER BY votes DESC",
        (pattern, pattern, pattern)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_products_suggest(query: str, limit: int = 6):
    """
    Ust bardaki arama kutusu icin hafif/hizli oneri listesi (canli dropdown).
    search_products ile ayni mantik ama sadece dropdown'da gosterilecek
    minimal alanlari ceker ve sonuc sayisini kucuk tutar (performans icin).
    """
    conn = get_connection()
    pattern = f"%{query.lower()}%"
    rows = conn.execute(
        """SELECT slug, original_name, summary_tr, thumbnail, votes FROM products
           WHERE (LOWER(title_tr) LIKE ? OR LOWER(summary_tr) LIKE ? OR LOWER(original_name) LIKE ?)
           AND (is_broken IS NULL OR is_broken = 0)
           ORDER BY votes DESC LIMIT ?""",
        (pattern, pattern, pattern, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# Turkce'de anlam tasimayan, arama sinyali olarak ise yaramayan kok kelimeler.
# AI Danismani'na dogal dil cumleleri geldiginde ("hangi arac isimi cozer" gibi)
# bu kelimeler filtrelenir, geriye anlamli terimler kalir.
_ADVISOR_STOPWORDS = {
    "bir", "bu", "şu", "o", "ve", "veya", "ile", "için", "gibi", "kadar", "de", "da",
    "ne", "nasıl", "hangi", "mi", "mı", "mu", "mü", "var", "yok", "çok", "az",
    "istiyorum", "istiyorsun", "istiyoruz", "lazım", "gerekiyor", "gerek",
    "yapmak", "yapmam", "yapmalıyım", "bana", "benim", "işimi", "işim",
}


def search_products_advisor(query: str, limit: int = 30):
    """
    AI Danismani icin aday urun havuzu bulur. Klasik search_products'tan farki:
    1) Dogal dil cumlelerini kelimelere ayirip anlamli terimlerle OR araması yapar
       (literal tum-cumle eslesmesi yerine).
    2) Hicbir kelime eslesmezse BOS DONMEZ - en populer urunlerden genis bir havuz
       dondurur, boylece LLM'e her zaman uzerinde akil yurutebilecegi bir aday
       kumesi verilir (LLM'e hic sormadan "bulunamadi" denmesi onlenir).
    """
    words = [w.strip(".,!?").lower() for w in query.split() if len(w.strip(".,!?")) > 2]
    meaningful = [w for w in words if w not in _ADVISOR_STOPWORDS]

    conn = get_connection()
    results = []
    if meaningful:
        like_clauses = " OR ".join(
            ["LOWER(title_tr) LIKE ? OR LOWER(summary_tr) LIKE ? OR LOWER(tags) LIKE ? OR LOWER(topics) LIKE ? OR LOWER(why_use_it) LIKE ?"] * len(meaningful)
        )
        params = []
        for w in meaningful:
            p = f"%{w}%"
            params.extend([p, p, p, p, p])
        rows = conn.execute(
            f"SELECT * FROM products WHERE ({like_clauses}) AND (is_broken IS NULL OR is_broken = 0) ORDER BY votes DESC LIMIT ?",
            params + [limit]
        ).fetchall()
        results = [dict(r) for r in rows]

    if not results:
        # Hicbir kelime eslesmedi - LLM'in secim yapabilecegi genis/populer bir havuz sun.
        rows = conn.execute(
            "SELECT * FROM products WHERE (is_broken IS NULL OR is_broken = 0) ORDER BY votes DESC LIMIT ?", (limit,)
        ).fetchall()
        results = [dict(r) for r in rows]

    conn.close()
    return results


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
    """
    Benzer araclari LLM KULLANMADAN, agirlikli bir skorla bulur:
    topic ortakligi (en yuksek agirlik) + pricing_type eslesmesi +
    platform eslesmesi + tag overlap. Boylece "ChatGPT alternatifi" ararken
    LLM'in konu disi bir arac onermesi (or. Slack) riski ortadan kalkar -
    tum eslesme kriterleri deterministik/kod tabanlidir.

    NOT: "AI" gibi urunlerin cogunda gecen asiri genel topic'ler
    (toplam urunun >%15'inde varsa) eslesme agirligina KATILMAZ - yoksa
    "her ikisi de AI etiketli" diye alakasiz urunler (or. ChatGPT + ClickUp)
    yanlis pozitif eslesir.
    """
    conn = get_connection()
    total_count = dict(conn.execute("SELECT COUNT(*) as cnt FROM products").fetchone())["cnt"] or 1
    topic_rows = conn.execute(
        "SELECT topics FROM products WHERE topics IS NOT NULL AND topics != ''"
    ).fetchall()
    topic_freq = {}
    for row in topic_rows:
        for t in dict(row)["topics"].split(","):
            t = t.strip()
            if t:
                topic_freq[t] = topic_freq.get(t, 0) + 1
    generic_topics = {t for t, cnt in topic_freq.items() if cnt / total_count > 0.15}
    # Frekans esigi dusuk cikan ama anlamca yine de asiri genel olan topic'ler
    # (or. "Uretkenlik" hem ChatGPT'de hem ClickUp'ta var ama ikisi alakasiz arac).
    generic_topics |= {
        "Uretkenlik", "Productivity", "AI", "Artificial Intelligence",
        "API", "Vercel Day", "Tech", "SaaS", "GitHub", "Business",
    }

    product = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not product:
        conn.close()
        return []
    product = dict(product)
    all_topics = [t.strip() for t in (product.get("topics") or "").split(",") if t.strip()]
    topics = [t for t in all_topics if t not in generic_topics] or all_topics
    if not topics:
        conn.close()
        return []
    tags = set(t.strip().lower() for t in (product.get("tags") or "").split(",") if t.strip())
    pricing = (product.get("pricing_type") or "").strip()
    platforms = set(p.strip().lower() for p in (product.get("platforms") or "").split(",") if p.strip())

    like_clauses = " OR ".join(["topics LIKE ?"] * len(topics))
    params = [f"%{t}%" for t in topics] + [product_id]
    rows = conn.execute(
        f"SELECT * FROM products WHERE ({like_clauses}) AND id != ? AND (is_broken IS NULL OR is_broken = 0)",
        params
    ).fetchall()
    conn.close()

    scored = []
    for r in rows:
        cand = dict(r)
        cand_topics = set(t.strip() for t in (cand.get("topics") or "").split(",") if t.strip())
        cand_tags = set(t.strip().lower() for t in (cand.get("tags") or "").split(",") if t.strip())
        cand_platforms = set(p.strip().lower() for p in (cand.get("platforms") or "").split(",") if p.strip())

        score = 0.0
        score += 10 * len(set(topics) & cand_topics)          # topic ortakligi (jenerik topic'ler haric) - en agirlikli
        score += 3 * len(tags & cand_tags)                    # tag overlap
        if pricing and cand.get("pricing_type") == pricing:   # ayni fiyat modeli
            score += 4
        if platforms and (platforms & cand_platforms):        # ortak platform
            score += 2
        score += min((cand.get("votes") or 0) / 100.0, 3)     # kucuk bir populerlik katkisi (tie-break)

        scored.append((score, cand))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:limit]]

def get_products_paginated(page=1, per_page=20, pricing_type=None):
    """Sayfalanmis urun listesi. pricing_type verilirse sadece o fiyat modeliyle filtreler."""
    conn = get_connection()
    offset = (page - 1) * per_page
    if pricing_type:
        rows = conn.execute(
            "SELECT * FROM products WHERE pricing_type = ? AND (is_broken IS NULL OR is_broken = 0) ORDER BY votes DESC LIMIT ? OFFSET ?",
            (pricing_type, per_page, offset)
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM products WHERE pricing_type = ? AND (is_broken IS NULL OR is_broken = 0)", (pricing_type,)
        ).fetchone()
    else:
        rows = conn.execute(
            "SELECT * FROM products WHERE (is_broken IS NULL OR is_broken = 0) ORDER BY votes DESC LIMIT ? OFFSET ?",
            (per_page, offset)
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) as cnt FROM products WHERE (is_broken IS NULL OR is_broken = 0)").fetchone()
    conn.close()
    return [dict(r) for r in rows], dict(total)["cnt"]


def save_collection(slug: str, title: str, description: str, items: list):
    """
    items: [{"product_id": int, "reason": str}, ...]
    Ayni slug varsa once eski collection_items silinip yenisi yazilir (guncelleme).
    """
    conn = get_connection()
    existing = conn.execute("SELECT id FROM collections WHERE slug = ?", (slug,)).fetchone()
    if existing:
        collection_id = dict(existing)["id"]
        conn.execute("UPDATE collections SET title=?, description=? WHERE id=?",
                     (title, description, collection_id))
        conn.execute("DELETE FROM collection_items WHERE collection_id=?", (collection_id,))
    else:
        cur = conn.execute(
            "INSERT INTO collections (slug, title, description, created_at) VALUES (?, ?, ?, ?)",
            (slug, title, description, datetime.utcnow().isoformat())
        )
        collection_id = cur.lastrowid

    order = 1
    for item in items:
        try:
            conn.execute(
                "INSERT INTO collection_items (collection_id, product_id, order_num, reason) VALUES (?, ?, ?, ?)",
                (collection_id, int(item["product_id"]), order, item.get("reason", ""))
            )
            order += 1
        except Exception as e:
            logger.warning(f"collection_item eklenemedi: {e}")
    conn.commit()
    conn.close()
    return collection_id


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

    # Kirik link isaretli urunler koleksiyon listesinden gizlenir.
    items = conn.execute("""
        SELECT p.*, ci.reason
        FROM collection_items ci
        JOIN products p ON p.id = ci.product_id
        WHERE ci.collection_id = ? AND (p.is_broken IS NULL OR p.is_broken = 0)
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
    update_quality_score(product_id)
