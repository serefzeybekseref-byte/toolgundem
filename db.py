"""
Veritabani katmani.
DATABASE_URL ortam degiskeni tanimliysa PostgreSQL (Supabase/Neon vb.) kullanilir,
tanimli degilse yerel SQLite (products.db) kullanilir.
Bu sayede kod hem lokal gelistirmede hem de Vercel gibi kalici disk sunmayan
serverless ortamlarda calisabilir hale gelir.
"""
import os
import re
import json
import time
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


_TABLES_WITH_ID_COLUMN = None  # lazy-loaded cache: {"PRODUCTS", "COMPARISONS", ...} - sadece gercekten 'id' kolonu olan tablolar


def _load_tables_with_id_column(raw_pg_conn):
    """
    information_schema'dan gercekte 'id' kolonu olan tablolarin listesini ceker ve modul
    seviyesinde onbelleğe alir. Bu, INSERT sonrasi 'RETURNING id' eklerken hangi tablolarin
    id'siz oldugunu ELLE listelemek zorunda kalmamizi onler (ornegin daily_visits gibi
    birincil anahtari baska bir alan olan yeni bir tablo eklendiginde, elle whitelist
    guncellemeyi unutup ayni "column id does not exist" hatasina tekrar dusme riskini
    ortadan kaldirir - bkz. 20 Temmuz 2026 record_visit bug'i).
    """
    global _TABLES_WITH_ID_COLUMN
    try:
        cur = raw_pg_conn.cursor()
        cur.execute("SELECT table_name FROM information_schema.columns WHERE column_name = 'id' AND table_schema = 'public'")
        _TABLES_WITH_ID_COLUMN = {row[0].upper() for row in cur.fetchall()}
        cur.close()
    except Exception:
        # Sema okunamazsa guvenli varsayilan: bos kume -> RETURNING id hic eklenmez
        # (id donmemesi, "column id does not exist" ile istegi patlatmaktan daha az kotu).
        _TABLES_WITH_ID_COLUMN = set()


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
                global _TABLES_WITH_ID_COLUMN
                if _TABLES_WITH_ID_COLUMN is None:
                    _load_tables_with_id_column(self.raw)
                match = re.search(r"INTO\s+(\w+)", stripped)
                table_name = match.group(1) if match else None
                if table_name and table_name in _TABLES_WITH_ID_COLUMN:
                    converted += " RETURNING id"
            try:
                cur.execute(converted, params)
            except psycopg2.errors.DeadlockDetected:
                # Nadir ama gercek: birden fazla otomasyon/oturum ayni anda DB'ye
                # yaziyor olabilir. inject_globals() HER sayfada calistigi icin tek
                # bir deadlock tum siteyi 500'e dusurebiliyordu - kisa bekleyip bir
                # kez daha deniyoruz, cogu zaman diger islem o arada biter.
                logger.warning("Postgres deadlock, 0.4sn sonra tekrar deneniyor: %s", converted[:80])
                self.raw.rollback()
                time.sleep(0.4)
                cur = self.raw.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute(converted, params)
            return _PGCursorWrapper(cur)
        return self.raw.execute(sql, params)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        """Bir sorgu hata verdiginde (ozellikle Postgres'te) transaction'i temizler -
        aksi halde paylasilan istek-baglantisi 'bozuk transaction' durumunda kalir ve
        o istekteki SONRAKI TUM sorgular da patlar (bkz. 20 Temmuz 2026 record_visit bug'i)."""
        try:
            self.raw.rollback()
        except Exception:
            pass

    def close(self):
        # Istek-basi paylasilan baglantilar tek tek kapatilmaz;
        # gercek kapama Flask'in teardown_appcontext'inde yapilir.
        if not self.shared:
            self.raw.close()


def _open_raw_connection(shared):
    if USE_POSTGRES:
        raw = psycopg2.connect(DATABASE_URL, connect_timeout=15)
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
            error_count INTEGER,
            budget REAL,
            success INTEGER,
            failed INTEGER,
            skipped INTEGER,
            retry INTEGER,
            llm_tokens INTEGER,
            llm_cost REAL,
            duration INTEGER
        )
    """)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS content_tasks (
            id {pk},
            product_id INTEGER,
            task_type TEXT,
            status TEXT,
            priority_score INTEGER DEFAULT 0,
            score_details TEXT,
            reason TEXT,
            retry_count INTEGER DEFAULT 0,
            last_error TEXT,
            estimated_cost REAL,
            created_at TEXT,
            started_at TEXT,
            finished_at TEXT,
            FOREIGN KEY (product_id) REFERENCES products (id)
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
        CREATE TABLE IF NOT EXISTS daily_visits (
            visit_date TEXT PRIMARY KEY,
            count INTEGER DEFAULT 0
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
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS guides (
            id {pk},
            slug TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            meta_description TEXT,
            excerpt TEXT,
            content_html TEXT,
            related_topic TEXT,
            related_tool_slugs TEXT,
            related_comparison_slugs TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    # guides tablosu daha once related_tool_slugs/related_comparison_slugs olmadan
    # olusturulmus olabilir - zaten varsa hatasiz gecilir.
    for col_name, col_type in [("related_tool_slugs", "TEXT"), ("related_comparison_slugs", "TEXT"), ("faq_json", "TEXT"), ("tools_json", "TEXT")]:
        if USE_POSTGRES:
            conn.execute(f"ALTER TABLE guides ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
        else:
            try:
                conn.execute(f"ALTER TABLE guides ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                pass

    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS audit_flags (
            id {pk},
            product_id INTEGER,
            reason TEXT NOT NULL,
            detected_at TEXT NOT NULL,
            resolved INTEGER DEFAULT 0,
            resolved_at TEXT
        )
    """)

    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS product_generation_queue (
            id {pk},
            name TEXT NOT NULL,
            normalized_name TEXT,
            source TEXT,
            priority TEXT DEFAULT 'Medium',
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            processed_at TEXT
        )
    """)

    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS outbound_click_events (
            id {pk},
            event_uuid TEXT UNIQUE NOT NULL,
            session_id TEXT,
            product_id INTEGER NOT NULL,
            clicked_at TEXT NOT NULL,
            destination_type TEXT NOT NULL,
            referrer TEXT NOT NULL,
            search_query TEXT,
            country TEXT DEFAULT 'Unknown',
            device TEXT NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products (id)
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
        ("is_showcase", "INTEGER DEFAULT 0"),
        ("last_checked_at", "TEXT"),
        ("is_broken", "INTEGER DEFAULT 0"),
        ("quality_score", "INTEGER DEFAULT 0"),
        ("gallery", "TEXT"),
        ("broken_reason", "TEXT"),
        ("broken_streak", "INTEGER DEFAULT 0"),
    ]
    for col_name, col_type in new_columns:
        if USE_POSTGRES:
            conn.execute(f"ALTER TABLE products ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
        else:
            try:
                conn.execute(f"ALTER TABLE products ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                pass

    # comparison_items icin best_for_type enum kolonu (bkz. classify_best_for).
    if USE_POSTGRES:
        conn.execute("ALTER TABLE comparison_items ADD COLUMN IF NOT EXISTS best_for_type TEXT")
    else:
        try:
            conn.execute("ALTER TABLE comparison_items ADD COLUMN best_for_type TEXT")
        except sqlite3.OperationalError:
            pass

    if USE_POSTGRES:
        conn.execute("ALTER TABLE outbound_click_events ADD COLUMN IF NOT EXISTS session_started_at TEXT")
    else:
        try:
            conn.execute("ALTER TABLE outbound_click_events ADD COLUMN session_started_at TEXT")
        except sqlite3.OperationalError:
            pass

    # Pipeline runs extension
    pipeline_new_cols = [
        ("budget", "REAL"),
        ("success", "INTEGER"),
        ("failed", "INTEGER"),
        ("skipped", "INTEGER"),
        ("retry", "INTEGER"),
        ("llm_tokens", "INTEGER"),
        ("llm_cost", "REAL"),
        ("duration", "INTEGER")
    ]
    for col_name, col_type in pipeline_new_cols:
        if USE_POSTGRES:
            conn.execute(f"ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
        else:
            try:
                conn.execute(f"ALTER TABLE pipeline_runs ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                pass

    conn.commit()
    conn.close()


# Karsilastirma kartlarindaki "Kim icin?" rozeti icin sabit enum.
# Onceki surumde bu siniflandirma template icinde (Jinja) satir satir
# anahtar kelime eslestirmesiyle yapiliyordu - bu kirilgan (ör. "ücretsiz"
# yerine "bedava"/"free" gecerse eslesmiyordu) ve her render'da tekrar
# hesaplaniyordu. Artik tek yerde (burada) siniflandirilip veritabaninda
# saklaniyor; template sadece enum -> rozet eslemesi yapar.
BEST_FOR_TYPES = {
    "general":     ("🏆", "En iyi genel kullanım"),
    "free":        ("💰", "En uygun fiyat"),
    "developer":   ("👨‍💻", "Geliştiriciler için"),
    "designer":    ("🎨", "Tasarımcılar için"),
    "beginner":    ("🚀", "Yeni başlayanlar için"),
    "enterprise":  ("🏢", "Kurumsal kullanım"),
    "education":   ("🎓", "Eğitim için"),
    "marketing":   ("📣", "Pazarlama için"),
    "video":       ("🎬", "Video için"),
    "audio":       ("🎙️", "Ses için"),
}

_BEST_FOR_KEYWORDS = {
    "free": ["ucret", "ücret", "fiyat", "uygun", "bedava", "free", "ekonomik"],
    "beginner": ["baslang", "başlang", "yeni baslayan", "kolay", "basit", "acemi"],
    "developer": ["gelistir", "geliştir", "kod", "developer", "yazilim", "yazılım", "api"],
    "designer": ["tasarim", "tasarım", "gorsel", "görsel", "design", "grafik"],
    "enterprise": ["kurumsal", "sirket", "şirket", "enterprise", "ekip", "takim", "takım"],
    "education": ["egitim", "eğitim", "ogrenci", "öğrenci", "akademik", "okul"],
    "marketing": ["pazarlama", "marketing", "reklam", "sosyal medya"],
    "video": ["video", "film", "montaj"],
    "audio": ["ses ", "muzik", "müzik", "podcast", "seslendirme"],
}


def classify_best_for(text: str, is_first_rank: bool = False) -> str:
    """
    best_for aciklama metnini BEST_FOR_TYPES anahtarlarindan birine esler.
    Hicbir kelime eslesmezse: ilk sirada ise 'general', degilse None doner
    (template rozet gostermez, sadece metni gosterir - hatali/uydurma rozet
    vermektense rozetsiz birakmak tercih edilir).
    """
    if not text:
        return "general" if is_first_rank else None
    t = text.lower()
    for type_key, keywords in _BEST_FOR_KEYWORDS.items():
        if any(kw in t for kw in keywords):
            return type_key
    return "general" if is_first_rank else None


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

    # PH bu urun icin ayri galeri gorseli sunmuyorsa (media alani bos/video vb.),
    # detay sayfasindaki "ekran goruntusu" bolumu bomboş kalmasin diye gercek
    # thumbnail'i (favicon degilse) tek bir galeri ogesi olarak kullaniriz.
    gallery_list = list(product.get("gallery", []) or [])
    thumb = product.get("thumbnail")
    if not gallery_list and thumb and "google.com/s2/favicons" not in thumb:
        gallery_list = [thumb]

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
        ",".join(gallery_list),
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


def add_audit_flag(product_id, reason: str, conn=None):
    """Bir denetim script'i (foreign_content_audit.py vb.) sorun bulunca cagirir.
    Ayni urun+reason zaten acik (resolved=0) ise tekrar eklemez (idempotent).
    conn verilirse (toplu tarama icin) o baglantiyi kullanir, commit etmez -
    caginin sonunda caller commit etmeli. conn verilmezse kendi baglantisini acar/kapatir."""
    from datetime import datetime
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM audit_flags WHERE product_id = ? AND reason = ? AND resolved = 0",
        (product_id, reason)
    ).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO audit_flags (product_id, reason, detected_at, resolved) VALUES (?, ?, ?, 0)",
            (product_id, reason, datetime.utcnow().isoformat())
        )
        if own_conn:
            conn.commit()
    if own_conn:
        conn.close()


def resolve_audit_flag(product_id, reason: str, conn=None):
    from datetime import datetime
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    conn.execute(
        "UPDATE audit_flags SET resolved = 1, resolved_at = ? WHERE product_id = ? AND reason = ? AND resolved = 0",
        (datetime.utcnow().isoformat(), product_id, reason)
    )
    if own_conn:
        conn.commit()
        conn.close()


def add_to_generation_queue(name: str, source: str, priority: str = "Medium", conn=None):
    """Henuz urun sayfasi olmayan ama bir karsilastirmada/koleksiyonda gecen bir aracı
    'uretim kuyruguna' ekler. Ayni normalized_name zaten pending/done ise tekrar eklemez
    (idempotent) - sadece source bilgisini birlestirir (birden fazla karsilastirmadan
    referans aliyorsa hepsi tek kayitta gorunsun)."""
    from datetime import datetime
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    norm = normalize_name(name)
    existing = conn.execute(
        "SELECT id, source FROM product_generation_queue WHERE normalized_name = ? AND status != 'done'",
        (norm,)
    ).fetchone()
    if existing:
        existing = dict(existing)
        existing_sources = [s.strip() for s in (existing.get("source") or "").split("|") if s.strip()]
        if source not in existing_sources:
            existing_sources.append(source)
            conn.execute(
                "UPDATE product_generation_queue SET source = ? WHERE id = ?",
                ("|".join(existing_sources), existing["id"])
            )
    else:
        conn.execute(
            "INSERT INTO product_generation_queue (name, normalized_name, source, priority, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
            (name, norm, source, priority, datetime.utcnow().isoformat())
        )
    if own_conn:
        conn.commit()
        conn.close()


def get_generation_queue(status: str = "pending"):
    conn = get_connection()
    if status:
        rows = conn.execute(
            "SELECT * FROM product_generation_queue WHERE status = ? ORDER BY priority ASC, created_at ASC", (status,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM product_generation_queue ORDER BY priority ASC, created_at ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_queue_item(queue_id: int, status: str):
    from datetime import datetime
    conn = get_connection()
    conn.execute(
        "UPDATE product_generation_queue SET status = ?, processed_at = ? WHERE id = ?",
        (status, datetime.utcnow().isoformat(), queue_id)
    )
    conn.commit()
    conn.close()


def record_visit():
    """Her sayfa istegi icin bugunun ziyaret sayacini bir artirir (UPSERT).
    Agir olmasin diye tek satirlik bir counter - detayli per-page log tutmuyor.
    Bu fonksiyon KESINLIKLE sayfa isteğini bozmamali (analytics kritik degil) - hata
    olursa yutulur, AMA once conn.rollback() cagrilir. Aksi halde paylasilan istek-baglantisi
    "bozuk transaction" durumunda kalir ve ayni istekteki SONRAKI TUM sorgular da patlar
    (bkz. 20 Temmuz 2026 record_visit bug'i - sadece exception yutmak yeterli degildi)."""
    from datetime import date
    today = date.today().isoformat()
    conn = get_connection()
    try:
        if USE_POSTGRES:
            conn.execute("""
                INSERT INTO daily_visits (visit_date, count) VALUES (?, 1)
                ON CONFLICT (visit_date) DO UPDATE SET count = daily_visits.count + 1
            """, (today,))
        else:
            conn.execute("""
                INSERT INTO daily_visits (visit_date, count) VALUES (?, 1)
                ON CONFLICT(visit_date) DO UPDATE SET count = count + 1
            """, (today,))
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("record_visit basarisiz oldu, transaction geri alindi")
    finally:
        conn.close()


def get_visit_stats():
    """Admin paneli icin: bugun, son 7 gun, toplam ziyaret."""
    from datetime import date, timedelta
    conn = get_connection()
    today = date.today().isoformat()
    week_ago = (date.today() - timedelta(days=7)).isoformat()

    today_row = conn.execute("SELECT count FROM daily_visits WHERE visit_date = ?", (today,)).fetchone()
    today_count = dict(today_row)["count"] if today_row else 0

    week_row = conn.execute(
        "SELECT COALESCE(SUM(count), 0) as c FROM daily_visits WHERE visit_date >= ?", (week_ago,)
    ).fetchone()
    week_count = dict(week_row)["c"]

    total_row = conn.execute("SELECT COALESCE(SUM(count), 0) as c FROM daily_visits").fetchone()
    total_count = dict(total_row)["c"]

    conn.close()
    return {"today": today_count, "last_7_days": week_count, "total": total_count}


def get_all_subscribers():
    """Admin paneli icin: tum abonelerin (aktif) e-posta listesi + tarih."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT email, subscribed_at, is_active FROM subscribers ORDER BY subscribed_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_showcase_products(limit=4):
    """Admin panelinden 'Vitrinde Goster' ile isaretlenmis urunleri dondurur.
    Vitrin widget'i bunlari, garantili affiliate kartlarinin (NordVPN/NordPass)
    yanina, editoryel/organik secim olarak ekler."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, slug, original_name, thumbnail, summary_tr FROM products "
        "WHERE is_showcase = 1 ORDER BY quality_score DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def toggle_showcase(product_id: int) -> bool:
    """Bir urunun vitrin durumunu tersine cevirir, yeni durumu dondurur."""
    conn = get_connection()
    row = conn.execute("SELECT is_showcase FROM products WHERE id = ?", (product_id,)).fetchone()
    if not row:
        conn.close()
        return False
    new_val = 0 if dict(row)["is_showcase"] else 1
    conn.execute("UPDATE products SET is_showcase = ? WHERE id = ?", (new_val, product_id))
    conn.commit()
    conn.close()
    return bool(new_val)


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

    affiliate_count = dict(conn.execute(
        "SELECT COUNT(*) as c FROM products WHERE affiliate_url IS NOT NULL AND affiliate_url != ''"
    ).fetchone())["c"]
    affiliate_coverage_pct = round((affiliate_count / total_products * 100), 1) if total_products else 0

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

    queue_rows = conn.execute(
        "SELECT priority, COUNT(*) as c FROM product_generation_queue WHERE status = 'pending' GROUP BY priority"
    ).fetchall()
    generation_queue = {dict(r)["priority"]: dict(r)["c"] for r in queue_rows}

    conn.close()
    return {
        "total_products": total_products,
        "avg_quality": avg_quality,
        "quality_buckets": quality_buckets,
        "broken_links": broken_links,
        "never_checked": never_checked,
        "affiliate_count": affiliate_count,
        "affiliate_coverage_pct": affiliate_coverage_pct,
        "total_comparisons": total_comparisons,
        "total_collections": total_collections,
        "top_topics": top_topics_list,
        "recent": recent,
        "pricing_breakdown": pricing_breakdown,
        "generation_queue": generation_queue,
    }


def get_content_os_dashboard():
    """Content OS admin paneli icin kuyruk ve saglik verilerini dondurur.
    AFFILIATE gorevleri otomatik islenmiyor (bilincli tasarim - gercek affiliate linki
    eklemek insan/is karari gerektirir), bu yuzden 'otomasyon kuyrugu' (tasks/stats)
    disinda, ayri bir 'is karari bekleyenler' listesi (affiliate_opportunities) olarak
    dondurulur - aksi halde hicbir zaman islenmeyecek kalemler 'bekleyen otomasyon isi'
    gibi gorunup yaniltici olurdu."""
    conn = get_connection()

    # Otomatik islenebilir gorevler (GUIDE/REFRESH) - gercek otomasyon kuyrugu
    tasks = conn.execute("""
        SELECT t.*, p.original_name, p.slug
        FROM content_tasks t
        JOIN products p ON t.product_id = p.id
        WHERE t.status = 'PENDING' AND t.task_type IN ('GUIDE', 'REFRESH')
        ORDER BY t.priority_score DESC
        LIMIT 20
    """).fetchall()

    # AFFILIATE: otomatik islenmez, ayri "is karari bekleyenler" listesi
    affiliate_opportunities = conn.execute("""
        SELECT t.*, p.original_name, p.slug
        FROM content_tasks t
        JOIN products p ON t.product_id = p.id
        WHERE t.status = 'PENDING' AND t.task_type = 'AFFILIATE'
        ORDER BY t.priority_score DESC
        LIMIT 30
    """).fetchall()

    # Son calismalar
    runs = conn.execute("""
        SELECT * FROM pipeline_runs
        ORDER BY id DESC
        LIMIT 5
    """).fetchall()

    # Istatistikler - sadece otomatik islenebilir turler (GUIDE/REFRESH) sayilir,
    # AFFILIATE dahil edilirse "bekleyen" sayisi hep yuksek kalir ve yanlis alarm verir.
    stats = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as success,
            SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed
        FROM content_tasks
        WHERE task_type IN ('GUIDE', 'REFRESH')
    """).fetchone()

    conn.close()

    return {
        "tasks": [dict(t) for t in tasks],
        "affiliate_opportunities": [dict(a) for a in affiliate_opportunities],
        "runs": [dict(r) for r in runs],
        "stats": dict(stats)
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


def get_all_products_for_link_check():
    """
    check_links.py icin: kirik isaretli olanlar DAHIL tum urunleri dondurur.
    get_all_products()'tan farki budur - amac, daha once kirik isaretlenmis
    bir sitenin zamanla DUZELMIS olabilecegini de kontrol edip is_broken
    bayragini otomatik olarak geri True'dan False'a cevirebilmek (iyilesme tespiti).
    Aksi halde bir urun bir kez kirik isaretlendiginde sonsuza dek gizli kalirdi."""
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
            (comparison_id, rank, name, score, pricing, best_for, pros, cons, website, best_for_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            comparison_id, item["rank"], item["name"], item["score"],
            item.get("pricing", ""), item.get("best_for", ""),
            "|".join(item.get("pros", [])), "|".join(item.get("cons", [])),
            item.get("website", ""),
            item.get("best_for_type") or classify_best_for(item.get("best_for", ""), item["rank"] == 1),
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

def get_partner_products(limit: int = 6):
    """
    Ana sayfadaki 'Vitrin' (partner showcase) bolumu icin: is_partner=1
    isaretli, affiliate anlasmasi olan urunleri dondurur. Bu urunler ayrica
    normal kesif akisinda (trending, kategori vb.) da gorunmeye devam eder -
    vitrin sadece EK bir one cikarma, gizli/yaniltici degildir (rozetle
    acikca 'Sponsorlu/Partner' oldugu belirtilir - bkz. templates/index.html).
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM products
        WHERE is_partner = 1 AND (is_broken IS NULL OR is_broken = 0)
        ORDER BY created_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_broken_products():
    """
    'Graveyard' sayfasi icin: kirik isaretli urunleri gizlemek yerine
    seffaf bir listede gosteririz (bkz. Best-AI.org gibi buyuk dizinlerin
    guven pratikleri - sessizce silmek yerine 'artik aktif degil' diye
    isaretlemek kullanicida daha fazla guven yaratir).
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM products WHERE is_broken = 1 ORDER BY last_checked_at DESC"
    ).fetchall()
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


def mark_link_checked(product_id: int, is_broken: bool, reason: str = ""):
    """Broken-link kontrol scripti tarafindan kullanilir (bkz. check_links.py).
    reason: neden kirik isaretlendigini aciklar (ornek: '404', 'timeout', 'ssl_error', 'dns_error')

    ONEMLI: is_broken (kullaniciya gosterilen/gizleyen bayrak) TEK BIR basarisiz kontrolde
    hemen True olmaz. GitHub Actions runner'indan (veya hedef sitenin CDN'inden) kaynaklanan
    tek seferlik/gecici ag hatalari yuzunden yanlis pozitif riski var (ornek: Play.ht, Hour One -
    gercekte canli ama bir kontrolde ag hatasi aldi). Bunun icin bir 'streak' (art arda
    basarisizlik) sayaci tutulur: bir site YALNIZCA art arda en az 2 FARKLI calistirmada
    (haftalik workflow, yani gunler arayla) basarisiz olursa kullaniciya gizlenir.
    Tek seferlik basarisizlik sessizce sayaci artirir ama gizlemez."""
    BROKEN_STREAK_THRESHOLD = 2
    conn = get_connection()
    row = conn.execute("SELECT broken_streak FROM products WHERE id = ?", (product_id,)).fetchone()
    prev_streak = dict(row).get("broken_streak") or 0 if row else 0

    if is_broken:
        streak = prev_streak + 1
    else:
        streak = 0

    publicly_broken = streak >= BROKEN_STREAK_THRESHOLD
    conn.execute(
        "UPDATE products SET last_checked_at = ?, is_broken = ?, broken_reason = ?, broken_streak = ? WHERE id = ?",
        (datetime.utcnow().isoformat(), 1 if publicly_broken else 0,
         reason if publicly_broken else "", streak, product_id)
    )
    conn.commit()
    conn.close()
    update_quality_score(product_id)


def slugify_guide(text: str) -> str:
    return slugify(text)


def save_guide(slug: str, title: str, meta_description: str, excerpt: str, content_html: str,
               related_topic: str = "", related_tool_slugs=None, related_comparison_slugs=None,
               faq_json: str = None):
    """Ayni slug varsa gunceller (icerik tazeleme), yoksa yeni rehber olusturur.
    related_tool_slugs / related_comparison_slugs: liste ya da virgulle ayrilmis string olabilir.
    faq_json: [{"soru":..,"cevap":..}, ...] listesinin JSON string hali - FAQPage schema.org icin."""
    if isinstance(related_tool_slugs, (list, tuple)):
        related_tool_slugs = ",".join(related_tool_slugs)
    if isinstance(related_comparison_slugs, (list, tuple)):
        related_comparison_slugs = ",".join(related_comparison_slugs)
    if isinstance(faq_json, (list, tuple)):
        faq_json = json.dumps(faq_json, ensure_ascii=False)

    conn = get_connection()
    now = datetime.utcnow().isoformat()
    existing = conn.execute("SELECT id FROM guides WHERE slug = ?", (slug,)).fetchone()
    if existing:
        guide_id = dict(existing)["id"]
        conn.execute("""
            UPDATE guides SET title=?, meta_description=?, excerpt=?, content_html=?,
            related_topic=?, related_tool_slugs=?, related_comparison_slugs=?, faq_json=?, updated_at=? WHERE id=?
        """, (title, meta_description, excerpt, content_html, related_topic,
              related_tool_slugs or "", related_comparison_slugs or "", faq_json or "", now, guide_id))
    else:
        conn.execute("""
            INSERT INTO guides (slug, title, meta_description, excerpt, content_html, related_topic,
            related_tool_slugs, related_comparison_slugs, faq_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (slug, title, meta_description, excerpt, content_html, related_topic,
              related_tool_slugs or "", related_comparison_slugs or "", faq_json or "", now, now))
    conn.commit()
    conn.close()
    return slug


def get_related_guides(current_slug: str, related_topic: str = "", limit: int = 3):
    """Baska rehberleri onerir (once ayni related_topic, sonra en yeniler ile tamamlar)."""
    conn = get_connection()
    result = []
    if related_topic:
        rows = conn.execute(
            "SELECT * FROM guides WHERE related_topic = ? AND slug != ? ORDER BY created_at DESC LIMIT ?",
            (related_topic, current_slug, limit)
        ).fetchall()
        result = [dict(r) for r in rows]
    if len(result) < limit:
        exclude_slugs = [g["slug"] for g in result] + [current_slug]
        placeholders = ",".join("?" * len(exclude_slugs))
        rows = conn.execute(
            f"SELECT * FROM guides WHERE slug NOT IN ({placeholders}) ORDER BY created_at DESC LIMIT ?",
            (*exclude_slugs, limit - len(result))
        ).fetchall()
        result += [dict(r) for r in rows]
    conn.close()
    return result


def get_all_guides():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM guides ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_guide_by_slug(slug: str):
    conn = get_connection()
    row = conn.execute("SELECT * FROM guides WHERE slug = ?", (slug,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_guides_for_topic(topic: str):
    """Bir kategori sayfasinda gosterilecek ilgili rehber(ler)."""
    if not topic:
        return []
    conn = get_connection()
    rows = conn.execute("SELECT * FROM guides WHERE related_topic = ?", (topic,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_guides_for_tool_slug(slug: str):
    """Bir urun detay sayfasinda gosterilecek ilgili rehber(ler)."""
    if not slug:
        return []
    conn = get_connection()
    pattern = f"%{slug}%"
    rows = conn.execute("SELECT * FROM guides WHERE related_tool_slugs LIKE ?", (pattern,)).fetchall()
    conn.close()
    # LIKE alt-dize eslesmesi yanlis pozitif verebilir (orn. 'foo' slug'i 'foo-bar' icinde eslesir) -
    # virgulle ayirip tam eslesme kontrolu yapiyoruz.
    result = []
    for r in rows:
        r = dict(r)
        slugs = [s.strip() for s in (r.get("related_tool_slugs") or "").split(",")]
        if slug in slugs:
            result.append(r)
    return result


def get_guides_for_comparison_slug(slug: str):
    """Bir karsilastirma sayfasinda gosterilecek ilgili rehber(ler)."""
    if not slug:
        return []
    conn = get_connection()
    pattern = f"%{slug}%"
    rows = conn.execute("SELECT * FROM guides WHERE related_comparison_slugs LIKE ?", (pattern,)).fetchall()
    conn.close()
    result = []
    for r in rows:
        r = dict(r)
        slugs = [s.strip() for s in (r.get("related_comparison_slugs") or "").split(",")]
        if slug in slugs:
            result.append(r)
    return result


def get_products_by_slugs(slugs):
    """Bir slug listesindeki urunleri, listedeki sirayla dondurur (rehberdeki
    onerilen siralamayi korumak icin)."""
    if not slugs:
        return []
    conn = get_connection()
    placeholders = ",".join("?" * len(slugs))
    rows = conn.execute(
        f"SELECT * FROM products WHERE slug IN ({placeholders}) AND (is_broken IS NULL OR is_broken = 0)",
        slugs
    ).fetchall()
    conn.close()
    by_slug = {dict(r)["slug"]: dict(r) for r in rows}
    return [by_slug[s] for s in slugs if s in by_slug]


def get_comparisons_by_slugs(slugs):
    """Bir slug listesindeki karsilastirmalari, listedeki sirayla dondurur."""
    if not slugs:
        return []
    conn = get_connection()
    placeholders = ",".join("?" * len(slugs))
    rows = conn.execute(
        f"SELECT * FROM comparisons WHERE slug IN ({placeholders})", slugs
    ).fetchall()
    conn.close()
    by_slug = {dict(r)["slug"]: dict(r) for r in rows}
    return [by_slug[s] for s in slugs if s in by_slug]


def record_outbound_click_event(session_id, product_id, dest_type, referrer, search_query, country, device, session_started_at=None):
    """Yeni bir dışa yönlendirme (outbound click) olayını veritabanına kaydeder."""
    import uuid
    from datetime import datetime
    
    event_uuid = f"evt_{uuid.uuid4().hex}"
    clicked_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO outbound_click_events (
            event_uuid, session_id, product_id, clicked_at, destination_type, referrer, search_query, country, device, session_started_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (event_uuid, session_id, product_id, clicked_at, dest_type, referrer, search_query, country, device, session_started_at)
    )
    conn.commit()
    conn.close()


def get_top_clicked_tools_stats(days=30):
    """
    En çok tıklanan araçları, tıklama sayılarını, 
    7 günlük trendlerini (son 7 gün vs önceki 7 gün) ve affiliate durumunu hesaplar.
    """
    from datetime import datetime, timedelta
    conn = get_connection()
    
    now = datetime.utcnow()
    t30 = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t7 = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t14 = (now - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    sql = """
        SELECT 
            p.id, p.original_name, p.slug, p.affiliate_url, p.is_partner,
            COUNT(e.id) as clicks_count
        FROM products p
        JOIN outbound_click_events e ON p.id = e.product_id
        WHERE e.clicked_at >= ?
        GROUP BY p.id, p.original_name, p.slug, p.affiliate_url, p.is_partner
        ORDER BY clicks_count DESC
        LIMIT 10
    """
    rows = conn.execute(sql, (t30,)).fetchall()
    top_tools = [dict(r) for r in rows]

    # ONEMLI: eskiden her arac icin 2 AYRI sorgu atiliyordu (10 arac = 21 sorgu).
    # Simdi tum araclarin son-7-gun ve onceki-7-gun sayilarini TEK sorguda,
    # CASE WHEN ile grupluyoruz.
    tool_ids = [t["id"] for t in top_tools]
    trend_map = {}
    if tool_ids:
        placeholders = ",".join(["?"] * len(tool_ids))
        trend_sql = f"""
            SELECT product_id,
                SUM(CASE WHEN clicked_at >= ? THEN 1 ELSE 0 END) as c7,
                SUM(CASE WHEN clicked_at >= ? AND clicked_at < ? THEN 1 ELSE 0 END) as c_prev
            FROM outbound_click_events
            WHERE product_id IN ({placeholders})
            GROUP BY product_id
        """
        trend_rows = conn.execute(trend_sql, [t7, t14, t7] + tool_ids).fetchall()
        for r in trend_rows:
            r = dict(r)
            trend_map[r["product_id"]] = {"c7": r["c7"] or 0, "c_prev": r["c_prev"] or 0}

    for tool in top_tools:
        p_id = tool["id"]
        counts = trend_map.get(p_id, {"c7": 0, "c_prev": 0})
        c7 = counts["c7"]
        c_prev = counts["c_prev"]
        
        tool["clicks_last_7"] = c7
        tool["clicks_prev_7"] = c_prev
        
        if c_prev > 0:
            diff = c7 - c_prev
            percent = int((diff / c_prev) * 100)
            tool["trend_pct"] = f"{'+' if diff >= 0 else ''}{percent}%"
            tool["trend_dir"] = "up" if diff >= 0 else "down"
        else:
            tool["trend_pct"] = f"+{c7 * 100}%" if c7 > 0 else "0%"
            tool["trend_dir"] = "up" if c7 > 0 else "flat"
            
    conn.close()
    return top_tools


def get_category_clicks_stats(days=30):
    """Kategorilerin tıklama hacimlerini döndürür."""
    from datetime import datetime, timedelta
    conn = get_connection()
    now = datetime.utcnow()
    t_start = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    sql = """
        SELECT p.topics, COUNT(e.id) as cnt
        FROM products p
        JOIN outbound_click_events e ON p.id = e.product_id
        WHERE e.clicked_at >= ?
        GROUP BY p.topics
    """
    rows = conn.execute(sql, (t_start,)).fetchall()
    
    cat_counts = {}
    for r in rows:
        topics_str = r["topics"] or ""
        cnt = r["cnt"] or 0
        for topic in topics_str.split(","):
            topic = topic.strip()
            if topic:
                cat_counts[topic] = cat_counts.get(topic, 0) + cnt
                
    sorted_cats = sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)
    conn.close()
    return [{"topic": t, "count": c} for t, c in sorted_cats[:10]]


def get_search_queries_stats(days=30):
    """Arama kelimeleri normalizasyonu yapılmış tıklama sayılarını listeler."""
    from datetime import datetime, timedelta
    conn = get_connection()
    now = datetime.utcnow()
    t_start = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    sql = """
        SELECT search_query, COUNT(id) as cnt
        FROM outbound_click_events
        WHERE clicked_at >= ? AND search_query IS NOT NULL AND search_query != ''
        GROUP BY search_query
        ORDER BY cnt DESC
        LIMIT 10
    """
    rows = conn.execute(sql, (t_start,)).fetchall()
    conn.close()
    return [{"query": r["search_query"], "clicks": r["cnt"]} for r in rows]


def get_zero_click_tools_stats(days=90):
    """Son 90 günde hiç tıklanmamış araçları getirir."""
    from datetime import datetime, timedelta
    conn = get_connection()
    now = datetime.utcnow()
    t_start = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    sql = """
        SELECT 
            p.id, p.original_name, p.slug, p.created_at, p.topics,
            MAX(e.clicked_at) as last_clicked
        FROM products p
        LEFT JOIN outbound_click_events e ON p.id = e.product_id
        WHERE p.is_broken IS NULL OR p.is_broken = 0
        GROUP BY p.id, p.original_name, p.slug, p.created_at, p.topics
        HAVING MAX(e.clicked_at) IS NULL OR MAX(e.clicked_at) < ?
        ORDER BY MAX(e.clicked_at) ASC NULLS FIRST, p.created_at ASC
        LIMIT 10
    """
    rows = conn.execute(sql, (t_start,)).fetchall()
    conn.close()
    
    result = []
    for r in rows:
        last_clicked = r["last_clicked"]
        if last_clicked:
            try:
                last_dt = datetime.strptime(last_clicked[:19], "%Y-%m-%dT%H:%M:%S")
                days_ago = (now - last_dt).days
                time_str = f"{days_ago} gün önce"
            except Exception:
                time_str = "Bilinmiyor"
        else:
            time_str = "Hiç tıklanmadı"
            
        result.append({
            "original_name": r["original_name"],
            "slug": r["slug"],
            "created_at": r["created_at"][:10] if r["created_at"] else "Bilinmiyor",
            "last_clicked_str": time_str,
            "topics": r["topics"]
        })
    return result


def get_orphan_opportunity_stats(days=30, limit=10):
    """En çok tıklanan ama rehberi, karşılaştırması veya koleksiyonu olmayan araçlar."""
    conn = get_connection()
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    t_start = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # 1. Koleksiyonlardaki tüm product_id'leri çek
    collection_pids = {r["product_id"] for r in conn.execute("SELECT product_id FROM collection_items").fetchall()}
    
    # 2. Rehberlerdeki tüm related_tool_slug'ları çek
    guides = conn.execute("SELECT related_tool_slugs FROM guides").fetchall()
    guide_slugs = set()
    for g in guides:
        for s in (g["related_tool_slugs"] or "").split(","):
            s = s.strip()
            if s:
                guide_slugs.add(s)
                
    # 3. Karşılaştırmalardaki tüm isimleri çek
    comp_names = {r["name"].strip().lower() for r in conn.execute("SELECT name FROM comparison_items").fetchall()}
    
    # 4. En çok tıklanan araçları çek
    sql = """
        SELECT 
            p.id, p.original_name, p.slug, p.topics,
            COUNT(e.id) as clicks_count
        FROM products p
        JOIN outbound_click_events e ON p.id = e.product_id
        WHERE e.clicked_at >= ?
        GROUP BY p.id, p.original_name, p.slug, p.topics
        ORDER BY clicks_count DESC
    """
    top_clicked = [dict(r) for r in conn.execute(sql, (t_start,)).fetchall()]
    
    orphans = []
    for tool in top_clicked:
        p_id = tool["id"]
        slug = tool["slug"]
        name_low = tool["original_name"].strip().lower()
        
        has_collection = p_id in collection_pids
        has_guide = slug in guide_slugs
        has_comparison = name_low in comp_names
        
        if not (has_collection and has_guide and has_comparison):
            orphans.append({
                "original_name": tool["original_name"],
                "slug": slug,
                "clicks": tool["clicks_count"],
                "has_collection": has_collection,
                "has_guide": has_guide,
                "has_comparison": has_comparison,
                "topics": tool["topics"]
            })
            if len(orphans) >= limit:
                break
                
    conn.close()
    return orphans


def get_raw_click_events_for_csv(days=30):
    from datetime import datetime, timedelta
    conn = get_connection()
    now = datetime.utcnow()
    t_start = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    sql = """
        SELECT 
            e.event_uuid, e.session_id, p.original_name as product_name, p.slug as product_slug,
            e.clicked_at, e.destination_type, e.referrer, e.search_query, e.country, e.device
        FROM outbound_click_events e
        JOIN products p ON e.product_id = p.id
        WHERE e.clicked_at >= ?
        ORDER BY e.clicked_at DESC
    """
    rows = conn.execute(sql, (t_start,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_daily_clicks_count(date_str):
    """Belirli bir gün (YYYY-MM-DD) içindeki toplam tıklama sayısını verir."""
    conn = get_connection()
    pattern = f"{date_str}%"
    row = conn.execute(
        "SELECT COUNT(id) as cnt FROM outbound_click_events WHERE clicked_at LIKE ? AND device != 'Bot'",
        (pattern,)
    ).fetchone()
    conn.close()
    return row["cnt"] if row else 0

def get_referrer_distribution(days=30, country='All', device='All'):
    from datetime import datetime, timedelta
    conn = get_connection()
    now = datetime.utcnow()
    t_start = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    query = "SELECT referrer, COUNT(id) as cnt FROM outbound_click_events WHERE clicked_at >= ?"
    params = [t_start]
    
    if country != 'All':
        query += " AND country = ?"
        params.append(country)
    if device != 'All':
        query += " AND device = ?"
        params.append(device)
        
    query += " GROUP BY referrer ORDER BY cnt DESC"
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    total = sum(r['cnt'] for r in rows)
    if total == 0:
        return []
        
    return [{'referrer': r['referrer'], 'count': r['cnt'], 'percent': int(round((r['cnt'] / total) * 100))} for r in rows]

def get_entry_exit_matrix(days=30, country='All', device='All'):
    from datetime import datetime, timedelta
    conn = get_connection()
    now = datetime.utcnow()
    t_start = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    query = "SELECT referrer, destination_type, COUNT(id) as cnt FROM outbound_click_events WHERE clicked_at >= ?"
    params = [t_start]
    
    if country != 'All':
        query += " AND country = ?"
        params.append(country)
    if device != 'All':
        query += " AND device = ?"
        params.append(device)
        
    query += " GROUP BY referrer, destination_type ORDER BY cnt DESC LIMIT 20"
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_multi_click_sessions(days=30, country='All', device='All'):
    from datetime import datetime, timedelta
    conn = get_connection()
    now = datetime.utcnow()
    t_start = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    query = "SELECT session_id, COUNT(id) as cnt, MIN(clicked_at) as first_click, MAX(clicked_at) as last_click FROM outbound_click_events WHERE clicked_at >= ?"
    params = [t_start]
    
    if country != 'All':
        query += " AND country = ?"
        params.append(country)
    if device != 'All':
        query += " AND device = ?"
        params.append(device)
        
    query += " AND session_id IS NOT NULL GROUP BY session_id HAVING COUNT(id) > 1 ORDER BY COUNT(id) DESC LIMIT 20"
    
    session_rows = [dict(r) for r in conn.execute(query, params).fetchall()]
    session_ids = [s["session_id"] for s in session_rows if s.get("session_id")]

    # Tek sorguda tum session'larin click'lerini cek (eskiden her session icin ayri
    # sorgu vardi - N+1 deseni, bkz. get_recent_user_journeys'deki ayni duzeltme).
    clicks_by_session = {}
    if session_ids:
        placeholders = ",".join(["?"] * len(session_ids))
        all_clicks = conn.execute(
            f"""SELECT o.session_id, o.clicked_at, o.referrer, p.original_name, o.destination_type
                FROM outbound_click_events o JOIN products p ON o.product_id = p.id
                WHERE o.session_id IN ({placeholders})
                ORDER BY o.session_id, o.clicked_at ASC""",
            session_ids
        ).fetchall()
        for row in all_clicks:
            row = dict(row)
            clicks_by_session.setdefault(row["session_id"], []).append(row)

    results = []
    for s in session_rows:
        sid = s['session_id']
        if not sid:
            continue
        clicks = clicks_by_session.get(sid, [])
        results.append({
            'session_id': sid[:8] + '...',
            'click_count': s.get('cnt', len(clicks)),
            'first_click': s['first_click'],
            'last_click': s['last_click'],
            'clicks': clicks
        })
        
    conn.close()
    return results

def get_recent_user_journeys(days=30, country='All', device='All', limit=50):
    from datetime import datetime, timedelta
    conn = get_connection()
    now = datetime.utcnow()
    t_start = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    query = "SELECT session_id, MAX(clicked_at) as last_click, MIN(session_started_at) as started_at, MAX(country) as country, MAX(device) as device FROM outbound_click_events WHERE clicked_at >= ? AND session_id IS NOT NULL"
    params = [t_start]
    
    if country != 'All':
        query += " AND country = ?"
        params.append(country)
    if device != 'All':
        query += " AND device = ?"
        params.append(device)
        
    query += " GROUP BY session_id ORDER BY MAX(clicked_at) DESC LIMIT ?"
    params.append(limit)
    
    sessions = conn.execute(query, params).fetchall()
    session_ids = [dict(s)["session_id"] for s in sessions if dict(s).get("session_id")]

    # ONEMLI: eskiden her session icin AYRI bir sorgu atiliyordu (N+1 sorgu deseni -
    # 50 session = 51 sorgu, admin panelinin "asiri yavas" olmasinin ana sebeplerinden
    # biriydi). Simdi TUM session'larin click'lerini TEK sorguda cekip Python'da
    # session_id'ye gore gruplu topluyoruz.
    clicks_by_session = {}
    if session_ids:
        placeholders = ",".join(["?"] * len(session_ids))
        all_clicks = conn.execute(
            f"""SELECT o.session_id, o.clicked_at, o.referrer, o.destination_type, p.original_name, o.search_query
                FROM outbound_click_events o JOIN products p ON o.product_id = p.id
                WHERE o.session_id IN ({placeholders})
                ORDER BY o.session_id, o.clicked_at ASC""",
            session_ids
        ).fetchall()
        for row in all_clicks:
            row = dict(row)
            clicks_by_session.setdefault(row["session_id"], []).append(row)

    journeys = []
    for s in sessions:
        s = dict(s)
        sid = s['session_id']
        if not sid:
            continue
        clicks = clicks_by_session.get(sid, [])
        
        click_count = len(clicks)
        if click_count == 1:
            intent = "Düşük"
            intent_val = 1
        elif click_count <= 3:
            intent = "Orta"
            intent_val = 2
        else:
            intent = "Yüksek"
            intent_val = 3
            
        time_to_first_click = None
        started_at = s['started_at']
        if started_at and clicks:
            try:
                start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                first_click_dt = datetime.fromisoformat(clicks[0]['clicked_at'].replace("Z", "+00:00"))
                diff = (first_click_dt - start_dt).total_seconds()
                if diff >= 0 and diff < 86400:
                    time_to_first_click = int(diff)
            except Exception:
                pass
                
        journeys.append({
            "session_id": sid[:8] + "...",
            "country": s['country'],
            "device": s['device'],
            "started_at": started_at,
            "time_to_first_click": time_to_first_click,
            "intent": intent,
            "intent_val": intent_val,
            "clicks": [dict(c) for c in clicks]
        })
    conn.close()
    return journeys

def get_average_time_to_first_click(days=30, country='All', device='All'):
    from datetime import datetime, timedelta
    conn = get_connection()
    now = datetime.utcnow()
    t_start = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    query = """
        SELECT session_id, MIN(session_started_at) as session_started_at, MIN(clicked_at) as first_click
        FROM outbound_click_events
        WHERE clicked_at >= ? AND session_started_at IS NOT NULL AND session_id IS NOT NULL
    """
    params = [t_start]
    
    if country != 'All':
        query += " AND country = ?"
        params.append(country)
    if device != 'All':
        query += " AND device = ?"
        params.append(device)
        
    query += " GROUP BY session_id"
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    total_seconds = 0
    valid_count = 0
    for r in rows:
        try:
            start_dt = datetime.fromisoformat(r['session_started_at'].replace("Z", "+00:00"))
            first_click_dt = datetime.fromisoformat(r['first_click'].replace("Z", "+00:00"))
            diff = (first_click_dt - start_dt).total_seconds()
            if 0 <= diff < 86400:
                total_seconds += diff
                valid_count += 1
        except Exception:
            pass
            
    if valid_count == 0:
        return 0
    return int(total_seconds / valid_count)

