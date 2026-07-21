import os
import json
import logging
import time
import requests
from dotenv import load_dotenv
load_dotenv()  # local'de .env'i yukler; production'da (Vercel) zaten env var'lar hazir, zararsiz.
from flask import Flask, render_template, abort, request, jsonify, Response, g
from db import (
    init_db, get_all_products, get_product_by_slug,
    get_all_comparisons, get_comparison_by_slug,
    get_trending_products, get_recent_products,
    get_products_by_topic, search_products, search_products_advisor, search_products_suggest,
    get_all_topics, get_similar_products, get_top_products_by_period,
    subscribe_email, unsubscribe_email,
    get_products_paginated, get_comparisons_for_product, get_collections_for_product,
    get_admin_stats, get_all_guides, get_guide_by_slug, get_related_guides,
    record_visit, get_visit_stats, get_all_subscribers,
    get_guides_for_topic, get_guides_for_tool_slug, get_guides_for_comparison_slug,
    get_products_by_slugs, get_comparisons_by_slugs,
    BEST_FOR_TYPES, record_outbound_click_event,
)
import os
from rules_engine import derive_use_cases_and_personas

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("toolgundem")

app = Flask(__name__, static_folder="static", static_url_path="/static")
# Statik dosyalar (CSS/JS/img) icin uzun sureli tarayici onbellegi. style.css ve favicon
# ?v={{ asset_version }} ile versiyonlu oldugu icin guvenle uzun tutulabilir; favicon.ico/
# icon-192.png gibi birkac dosya versiyonsuz kaldigi icin 1 yil yerine 30 gun (daha guvenli
# bir denge) seciliyor - bkz. inject_globals().
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 2592000  # 30 gun
init_db()

# Footer verileri (rehber/karsilastirma/konu listesi) icin bellek-ici onbellek.
# NOT: Vercel serverless ortaminda her "cold start" bu degeri sifirlar, ama ayni
# warm instance'da art arda gelen isteklerde (kullanicinin hizli sekme gecisleri gibi)
# gercek fayda saglar - 5 dakikada bir tazelenir.
_footer_cache = {"data": None, "ts": 0}
_home_cache = {"data": None, "ts": 0}
_simple_caches = {}


def cached(key, fn, ttl=300):
    """Genel amacli bellek-ici TTL onbellek. Nadiren degisen liste sayfalari
    (karsilastirma/koleksiyon/rehber listeleri vb.) icin kullanilir."""
    now = time.time()
    entry = _simple_caches.get(key)
    if entry is None or (now - entry["ts"] > ttl):
        _simple_caches[key] = {"data": fn(), "ts": now}
    return _simple_caches[key]["data"]


_TRACKED_ENDPOINTS = {
    "home", "detail", "category", "comparisons_list", "comparison_detail",
    "guides_list", "guide_detail", "collections_list", "collection_detail",
    "iletisim", "hakkimizda", "gizlilik", "kvkk", "kullanim-sartlari", "search"
}


BOT_KEYWORDS = [
    "googlebot", "bingbot", "yandexbot", "ahrefsbot", "semrushbot", "mj12bot",
    "gptbot", "claudebot", "perplexitybot", "bytespider", "applebot", "crawl",
    "spider", "slurp", "facebookexternalhit", "twitterbot", "linkedinbot", "ia_archiver"
]

def is_bot(user_agent_str):
    if not user_agent_str:
        return True
    ua = user_agent_str.lower()
    return any(bot in ua for bot in BOT_KEYWORDS)

def parse_device(user_agent_str):
    if not user_agent_str:
        return "Unknown"
    if is_bot(user_agent_str):
        return "Bot"
    ua = user_agent_str.lower()
    if "ipad" in ua or "tablet" in ua or ("android" in ua and "mobile" not in ua):
        return "Tablet"
    if "mobile" in ua or "android" in ua or "iphone" in ua or "ipod" in ua:
        return "Mobile"
    if "windows" in ua or "macintosh" in ua or "linux" in ua:
        return "Desktop"
    return "Unknown"

@app.before_request
def _track_visit():
    """Sadece gercek HTML sayfa yuklemelerini (beyaz listedeki endpoint'leri)
    tarayici cerezine gore tekillestirerek ziyaret sayacina ekler.
    Ayrıca kullanıcılara uzun vadeli anonim bir tg_session çerezi atar."""
    # tg_session çerezi yoksa oluştur (her istek için geçerli)
    session_id = request.cookies.get("tg_session")
    if not session_id:
        import uuid
        from datetime import datetime
        g._new_session_id = uuid.uuid4().hex
        g._new_session_started_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    if request.endpoint not in _TRACKED_ENDPOINTS:
        return
    from datetime import date
    today = date.today().isoformat()
    if request.cookies.get("tg_visited") == today:
        return  # bu tarayici bugun zaten sayildi, tekrar sayma
    try:
        record_visit()
    except Exception:
        pass
    g._mark_visit_cookie = today


@app.after_request
def _set_visit_cookie(response):
    """Oturum ve ziyaret çerezlerini tarayıcıya yazar."""
    today = getattr(g, "_mark_visit_cookie", None)
    if today:
        response.set_cookie("tg_visited", today, max_age=60 * 60 * 24, httponly=True, samesite="Lax", secure=True)
    
    new_session = getattr(g, "_new_session_id", None)
    if new_session:
        # tg_session çerezi 1 yıl (365 gün) saklanır
        response.set_cookie("tg_session", new_session, max_age=60 * 60 * 24 * 365, httponly=True, samesite="Lax", secure=True)
        new_started = getattr(g, "_new_session_started_at", None)
        if new_started:
            response.set_cookie("tg_session_started", new_started, max_age=60 * 60 * 24 * 365, httponly=True, samesite="Lax", secure=True)
    return response


@app.teardown_appcontext
def close_db_connection(exception=None):
    """Istek basi paylasilan DB baglantisini istek bitince gercekten kapatir."""
    conn = g.pop("_db_conn", None)
    if conn is not None:
        try:
            conn.raw.close()
        except Exception:
            pass


# --- Topic display labels ---
TOPIC_LABELS = {
    "AI": "Yapay Zeka",
    "Chatbot": "Sohbet Botları",
    "Gorsel": "Görsel Üretimi",
    "Video": "Video AI",
    "Kod": "Kodlama",
    "Yazi": "Yazı & İçerik",
    "Sunum": "Sunum",
    "Muzik": "Müzik & Ses",
    "Ses": "Ses & Konuşma",
    "SEO": "SEO",
    "Otomasyon": "Otomasyon",
    "Tasarim": "Tasarım",
    "Transkripsiyon": "Transkripsiyon",
    "Uretkenlik": "Üretkenlik",
    "Arastirma": "Araştırma",
    "NoCode": "No-Code",
    "Satis": "Satış & CRM",
    "Eticaret": "E-Ticaret",
    "Ceviri": "Çeviri",
    "WebSitesi": "Web Sitesi",
    "MusteriDestegi": "Müşteri Desteği",
    "Avatar": "Avatar & Dijital İnsan",
    "Veri": "Veri Analizi",
    "Vercel Day": "Vercel Day",
    "Artificial Intelligence": "Yapay Zeka",
    "Google": "Google",
    "Developer Tools": "Geliştirici Araçları",
    "GitHub": "GitHub",
    "Productivity": "Prodüktivite",
    "AcikKaynak": "Açık Kaynak",
    "Eposta": "E-posta",
    "Health & Fitness": "Sağlık & Fitness",
    "Games": "Oyun",
    "SaaS": "SaaS",
    "Education": "Eğitim",
    "Marketing": "Pazarlama",
    "Email": "E-posta",
    "Adobe": "Adobe",
    "UI": "Arayüz Tasarımı",
    "Business": "İş Dünyası",
    "Tech": "Teknoloji",
    "News": "Haber",
    "Sports": "Spor",
    "Online Learning": "Online Eğitim",
    "Investing": "Yatırım",
    "Task Management": "Görev Yönetimi",
    "Indie Games": "Bağımsız Oyunlar",
    "Photo editing": "Fotoğraf Düzenleme",
    "Medical": "Sağlık",
    "Open Source": "Açık Kaynak",
}

TOPIC_ICONS = {
    "AI": "🤖",
    "Chatbot": "💬",
    "Gorsel": "🎨",
    "Video": "🎬",
    "Kod": "💻",
    "Yazi": "✍️",
    "Sunum": "📊",
    "Muzik": "🎵",
    "Ses": "🎙️",
    "SEO": "📈",
    "Otomasyon": "⚡",
    "Tasarim": "🎯",
    "Transkripsiyon": "📝",
    "Uretkenlik": "🚀",
    "Arastirma": "🔬",
    "NoCode": "🧩",
    "Satis": "💰",
    "Eticaret": "🛒",
    "Ceviri": "🌍",
    "WebSitesi": "🌐",
    "MusteriDestegi": "🎧",
    "Avatar": "👤",
    "Veri": "📊",
    "Vercel Day": "▲",
    "Artificial Intelligence": "🤖",
    "Google": "🔍",
    "Developer Tools": "🛠️",
    "GitHub": "🐙",
    "Productivity": "📋",
    "AcikKaynak": "🔓",
    "Eposta": "📧",
    "Health & Fitness": "💪",
    "Games": "🎮",
    "SaaS": "☁️",
    "Education": "🎓",
    "Marketing": "📣",
    "Email": "📧",
    "Adobe": "🖌️",
    "UI": "🖼️",
    "Business": "💼",
    "Tech": "💡",
    "News": "📰",
    "Sports": "⚽",
    "Online Learning": "🎓",
    "Investing": "📈",
    "Task Management": "✅",
    "Indie Games": "🕹️",
    "Photo editing": "🖼️",
    "Medical": "⚕️",
    "Open Source": "🔓",
}

_FALLBACK_ICONS = ["✨", "🧩", "🔧", "🌐", "📦", "💡", "🎯", "🔹"]

# Ana sayfa "Ne yapmak istiyorsun?" CTA izgarasi - rules.json'daki ayni use_case
# sozlugunu (rules_engine.py) referans alir, boylece rule engine ile ayni dilde konusur.
# (etiket, ikon, hedef raw-topic)
USE_CASE_CTA = [
    ("Kod yazmak", "💻", "Kod"),
    ("Görsel üretmek", "🎨", "Gorsel"),
    ("Video üretmek", "🎬", "Video"),
    ("Ses üretmek", "🎙️", "Ses"),
    ("Sunum hazırlamak", "📊", "Sunum"),
    ("Yazı yazmak", "✍️", "Yazi"),
    ("Otomasyon kurmak", "⚡", "Otomasyon"),
    ("Pazarlama yapmak", "📣", "Marketing"),
]


def get_merged_topics():
    """
    get_all_topics() ham PH topic'lerini (AI, Artificial Intelligence gibi ayni
    Turkce etikete cevrilen ama farkli raw string olan ciftleri) TOPIC_LABELS
    uzerinden aynı goruntulenen etikette birlestirip sayilarini toplar.
    Boylece "Yapay Zeka" ayni ikonla iki kez degil, tek ve dogru sayiyla gorunur.
    NOT: Chip href'i hala en yuksek sayili HAM topic'e gider (kategori sayfasi
    o ham topic'e gore filtreliyor), sadece goruntu/sayim birlesiyor.
    """
    raw_topics = get_all_topics()  # [(raw_topic, count), ...]
    merged = {}
    for raw_topic, count in raw_topics:
        label = TOPIC_LABELS.get(raw_topic, raw_topic)
        if label not in merged:
            merged[label] = {"raw_topic": raw_topic, "label": label, "count": 0, "_best": 0}
        merged[label]["count"] += count
        if count > merged[label]["_best"]:
            merged[label]["_best"] = count
            merged[label]["raw_topic"] = raw_topic
    result = sorted(merged.values(), key=lambda x: x["count"], reverse=True)
    return result


def get_topic_icon(topic):
    if topic in TOPIC_ICONS:
        return TOPIC_ICONS[topic]
    idx = sum(ord(c) for c in topic) % len(_FALLBACK_ICONS)
    return _FALLBACK_ICONS[idx]


_COMPARISON_ICON_KEYWORDS = [
    ("pdf", "📄"), ("özgeçmiş", "📋"), ("cv", "📋"),
    ("logo", "🎨"), ("görsel", "🎨"), ("tasarım", "🎨"),
    ("müzik", "🎵"), ("ses", "🎙️"),
    ("toplantı", "📝"), ("transkripsiyon", "📝"), ("not", "📝"),
    ("video", "🎬"), ("görüntü", "🖼️"),
    ("kod", "⌨️"), ("yazılım", "⌨️"),
    ("sohbet", "💬"), ("chatbot", "💬"), ("asistan", "💬"),
    ("yazı", "✍️"), ("içerik", "✍️"),
    ("sunum", "📊"), ("slayt", "📊"),
    ("e-ticaret", "🛒"), ("satış", "💰"),
    ("web sitesi", "🌐"), ("seo", "📈"),
]


def get_comparison_icon(title):
    title_low = (title or "").lower()
    for keyword, icon in _COMPARISON_ICON_KEYWORDS:
        if keyword in title_low:
            return icon
    return "🏆"


def get_cta_url(product, type='website', ref='product'):
    """Tüm dışa yönlendirme linklerini /go/<slug> köprüsüne bağlar."""
    slug = product.get("slug")
    if not slug:
        return (product.get("affiliate_url") or "").strip() or product.get("website", "")
    from urllib.parse import urlencode
    params = {"type": type, "ref": ref}
    if ref == "search":
        q = request.args.get("q", "").strip()
        if q:
            params["q"] = q
    return f"/go/{slug}?{urlencode(params)}"


def get_cta_label(product):
    """Affiliate linki varsa donusumu tesvik eden bir CTA, yoksa notr 'Resmi Sitesi' etiketi."""
    if (product.get("affiliate_url") or "").strip():
        return "Ücretsiz Dene →"
    return "Resmi Sitesi →"


_TR_AYLAR = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]


def turkce_tarih(date_str):
    """'2026-07-16T...' formatindaki bir tarihi '16 Temmuz 2026' seklinde gosterir.
    Bos/gecersiz girdi icin None doner (template'te kosullu gizlemek icin)."""
    if not date_str:
        return None
    try:
        y, m, d = date_str[:10].split("-")
        return f"{int(d)} {_TR_AYLAR[int(m) - 1]} {y}"
    except (ValueError, IndexError):
        return None


@app.context_processor
def inject_globals():
    """Tum template'lerde kullanilabilecek global degiskenler.
    Footer verileri (guides/comparisons/topics) neredeyse hic degismedigi icin
    her sayfa renderinda yeniden sorgulamak yerine 5 dakikalik bellek-ici
    (in-memory) onbellek kullanilir - sekme/sayfa gecislerini belirgin hizlandirir."""
    now = time.time()
    if (_footer_cache["data"] is None) or (now - _footer_cache["ts"] > 300):
        _footer_cache["data"] = {
            "footer_guides": get_all_guides()[:5],
            "footer_comparisons": get_all_comparisons()[:5],
            "footer_topics": [(t["raw_topic"], t["count"]) for t in get_merged_topics()[:6]],
        }
        _footer_cache["ts"] = now
    footer_guides = _footer_cache["data"]["footer_guides"]
    footer_comparisons = _footer_cache["data"]["footer_comparisons"]
    footer_topics = _footer_cache["data"]["footer_topics"]
    try:
        # Vercel her deploy'da VERCEL_GIT_COMMIT_SHA'yi otomatik enjekte eder - bu deploy'a
        # gore gercekten degisir. Dosya mtime'ina guvenmiyoruz cunku Vercel'in build sureci
        # dosya zamanlarini sabit bir referansa normalize ediyor (asset_version hic degismiyordu,
        # tarayicilar CSS degisikliklerini asla gormuyordu - CLS fix'inin "calismamis" gorunmesinin
        # gercek nedeni buydu).
        asset_version = os.environ.get("VERCEL_GIT_COMMIT_SHA", "")[:10]
        if not asset_version:
            asset_version = str(int(os.path.getmtime(os.path.join(app.static_folder, "style.css"))))
    except OSError:
        asset_version = "1"
    return {
        "asset_version": asset_version,
        "topic_labels": TOPIC_LABELS,
        "topic_icons": TOPIC_ICONS,
        "get_topic_icon": get_topic_icon,
        "get_comparison_icon": get_comparison_icon,
        "get_cta_url": get_cta_url,
        "best_for_types": BEST_FOR_TYPES,
        "get_cta_label": get_cta_label,
        "turkce_tarih": turkce_tarih,
        "footer_guides": footer_guides,
        "footer_comparisons": footer_comparisons,
        "footer_topics": footer_topics,
        "adsense_publisher_id": os.getenv("ADSENSE_PUBLISHER_ID", ""),
    }


@app.route("/")
def home():
    now = time.time()
    if (_home_cache["data"] is None) or (now - _home_cache["ts"] > 300):
        trending = get_trending_products(limit=6)
        recent = get_recent_products(limit=6)
        trending_ids = [p["id"] for p in trending]
        weekly_top = get_top_products_by_period(days=7, limit=6, exclude_ids=trending_ids)
        monthly_top = get_top_products_by_period(days=30, limit=6, exclude_ids=trending_ids + [p["id"] for p in weekly_top])
        topics = get_merged_topics()
        comparisons = get_all_comparisons()

        # Get total product count for the stats section
        from db import get_connection
        from datetime import datetime, timezone, timedelta
        conn = get_connection()
        total_products = dict(conn.execute("SELECT COUNT(*) as cnt FROM products").fetchone())["cnt"]
        thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
        new_last_30d = dict(conn.execute(
            "SELECT COUNT(*) as cnt FROM products WHERE created_at >= ?", (thirty_days_ago,)
        ).fetchone())["cnt"]
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        new_today = dict(conn.execute(
            "SELECT COUNT(*) as cnt FROM products WHERE created_at >= ?", (today_str,)
        ).fetchone())["cnt"]
        conn.close()
        three_days_ago = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d")

        _home_cache["data"] = dict(
            trending=trending, recent=recent, weekly_top=weekly_top, monthly_top=monthly_top,
            topics=topics, comparisons=comparisons, total_products=total_products,
            new_last_30d=new_last_30d, new_today=new_today, new_cutoff=three_days_ago,
        )
        _home_cache["ts"] = now

    return render_template("index.html", use_case_cta=USE_CASE_CTA, **_home_cache["data"])


@app.route("/urun/<slug>")
def detail(slug):
    product = get_product_by_slug(slug)
    if not product:
        abort(404)
    similar = get_similar_products(product["id"], limit=4)
    related_comparisons = get_comparisons_for_product(product.get("normalized_name"))
    related_collections = get_collections_for_product(product.get("id"))
    related_guides = get_guides_for_tool_slug(product.get("slug"))
    tags = derive_use_cases_and_personas(product.get("topics", ""), product.get("tags", ""))
    return render_template(
        "detail.html", product=product, similar=similar,
        related_comparisons=related_comparisons,
        related_collections=related_collections,
        related_guides=related_guides,
        use_cases=tags["use_cases"], personas=tags["personas"],
    )


@app.route("/karsilastirma")
def comparisons_list():
    comparisons = cached("comparisons_list", get_all_comparisons)
    return render_template("comparisons.html", comparisons=comparisons)


@app.route("/rehber")
def guides_list():
    guides = cached("guides_list", get_all_guides)
    return render_template("guides.html", guides=guides)


@app.route("/rehber/<slug>")
def guide_detail(slug):
    guide = get_guide_by_slug(slug)
    if not guide:
        abort(404)
    related_tools = get_products_by_slugs(
        [s.strip() for s in (guide.get("related_tool_slugs") or "").split(",") if s.strip()]
    )
    related_comparisons = get_comparisons_by_slugs(
        [s.strip() for s in (guide.get("related_comparison_slugs") or "").split(",") if s.strip()]
    )
    related_guides = get_related_guides(slug, guide.get("related_topic") or "", limit=3)
    faq_list = []
    if guide.get("faq_json"):
        try:
            faq_list = json.loads(guide["faq_json"])
        except (json.JSONDecodeError, TypeError):
            faq_list = []
    return render_template(
        "guide_detail.html",
        guide=guide,
        related_tools=related_tools,
        related_comparisons=related_comparisons,
        related_guides=related_guides,
        faq_list=faq_list,
    )


@app.route("/abone/iptal")
def unsubscribe():
    """
    Bulten mailindeki 'abonelikten cik' linki. Token, e-postanin ADMIN_TOKEN ile
    imzalanmis kisa bir hash'i - baskasinin e-postasini token'sizi tahmin edip
    iptal edememesi icin (guvenlik degil, kotu niyetli spam-iptal engeli).
    """
    import hashlib
    email = (request.args.get("e") or "").strip().lower()
    token = request.args.get("t", "")
    expected = hashlib.sha256((email + os.environ.get("ADMIN_TOKEN", "")).encode()).hexdigest()[:16]
    if not email or token != expected:
        return render_template("message.html", title="Geçersiz bağlantı",
                                message="Bu abonelikten çıkma bağlantısı geçersiz veya süresi dolmuş."), 400
    unsubscribe_email(email)
    return render_template("message.html", title="Abonelikten çıktın",
                            message=f"{email} adresi bülten listemizden çıkarıldı. Fikrini değiştirirsen ana sayfadan tekrar abone olabilirsin.")


@app.route("/abone", methods=["POST"])
def subscribe():
    """Bulten kaydi - hem normal form submit (JS'siz) hem fetch/JSON destekler."""
    email = request.form.get("email") or (request.get_json(silent=True) or {}).get("email", "")
    result = subscribe_email(email)
    if result == "gecersiz":
        message = "Geçerli bir e-posta adresi girin."
    elif result == "zaten_var":
        message = "Zaten abonesin, teşekkürler!"
    else:
        message = "Teşekkürler! Abone oldun."

    if request.is_json or request.headers.get("X-Requested-With") == "fetch":
        return jsonify({"ok": result != "gecersiz", "message": message})

    from flask import redirect, url_for
    return redirect(request.referrer or url_for("home"))


@app.route("/karsilastirma/<slug>")
def comparison_detail(slug):
    comparison = get_comparison_by_slug(slug)
    if not comparison:
        abort(404)
    related_guides = get_guides_for_comparison_slug(slug)
    return render_template("comparison_detail.html", comparison=comparison, related_guides=related_guides)


@app.route("/kategori/<topic>")
def category(topic):
    # Vercel'in Python WSGI adaptoru bazi durumlarda path segmentini decode etmeden
    # iletiyor (yerel Flask dev server'dan farkli davraniyor) - bu yuzden topic
    # literal "%20" gibi encode edilmis karakterler icerebiliyor. unquote() zaten
    # decode edilmis bir deger icin no-op'tur, guvenli.
    from urllib.parse import unquote
    topic = unquote(topic)
    products = get_products_by_topic(topic)
    fiyat = request.args.get("fiyat", "").strip()
    if fiyat:
        products = [p for p in products if p.get("pricing_type") == fiyat]
    label = TOPIC_LABELS.get(topic, topic)
    icon = TOPIC_ICONS.get(topic, "📁")
    all_topics = get_merged_topics()
    related_guides = get_guides_for_topic(topic)
    return render_template(
        "category.html",
        topic=topic,
        topic_label=label,
        topic_icon=icon,
        products=products,
        all_topics=all_topics,
        related_guides=related_guides,
    )


@app.route("/iletisim")
def iletisim():
    return render_template("iletisim.html", page_title="İletişim")


@app.route("/hakkimizda")
def hakkimizda():
    return render_template("hakkimizda.html", page_title="Hakkımızda")


@app.route("/gizlilik")
def gizlilik():
    return render_template("gizlilik.html", page_title="Gizlilik Politikası", page_updated="17 Temmuz 2026")


@app.route("/kvkk")
def kvkk():
    return render_template("kvkk.html", page_title="KVKK Aydınlatma Metni", page_updated="17 Temmuz 2026")


@app.route("/kullanim-sartlari")
def kullanim_sartlari():
    return render_template("kullanim-sartlari.html", page_title="Kullanım Şartları", page_updated="17 Temmuz 2026")


@app.route("/ara")
def search():
    query = request.args.get("q", "").strip()
    results = []
    if query:
        results = search_products(query)
    return render_template("search.html", query=query, results=results)


@app.route("/api/search-suggest")
def api_search_suggest():
    """Ust bardaki arama kutusu icin canli/anlik oneri dropdown'u besler."""
    query = request.args.get("q", "").strip()
    if len(query) < 2:
        return jsonify({"results": []})
    results = search_products_suggest(query, limit=6)
    return jsonify({"results": results})


@app.route("/api/products")
def api_products():
    """Daha Fazla Yukle butonu icin JSON API."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    topic = request.args.get("topic", "").strip()
    pricing = request.args.get("pricing", "").strip()
    if topic:
        products = get_products_by_topic(topic)
        if pricing:
            products = [p for p in products if p.get("pricing_type") == pricing]
        # Manual pagination
        start = (page - 1) * per_page
        end = start + per_page
        paginated = products[start:end]
        total = len(products)
    else:
        paginated, total = get_products_paginated(page, per_page, pricing_type=pricing or None)
    return jsonify({
        "products": paginated,
        "page": page,
        "per_page": per_page,
        "total": total,
        "has_more": page * per_page < total,
    })


@app.route("/sitemap.xml")
def sitemap():
    from xml.sax.saxutils import escape
    from urllib.parse import quote
    products = get_all_products()
    comparisons = get_all_comparisons()
    topics = get_all_topics()
    from db import get_all_collections
    collections = get_all_collections()
    base = "https://" + request.host

    def loc(path):
        # Ozel karakterler (&, <, >, ', ") hem URL hem XML acisindan escape edilir,
        # boylece sitemap "cozumleme hatasi" (parse error) vermez.
        return escape(f"{base}{path}")

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    # Home
    xml += f'  <url><loc>{loc("/")}</loc><priority>1.0</priority></url>\n'
    # Products
    for p in products:
        xml += f'  <url><loc>{loc("/urun/" + quote(str(p["slug"])))}</loc></url>\n'
    # Comparisons
    xml += f'  <url><loc>{loc("/karsilastirma")}</loc><priority>0.8</priority></url>\n'
    for c in comparisons:
        xml += f'  <url><loc>{loc("/karsilastirma/" + quote(str(c["slug"])))}</loc></url>\n'
    # Categories
    for topic, count in topics:
        xml += f'  <url><loc>{loc("/kategori/" + quote(str(topic)))}</loc></url>\n'
    # Collections
    for col in collections:
        xml += f'  <url><loc>{loc("/koleksiyon/" + quote(str(col["slug"])))}</loc></url>\n'
    # Guides
    xml += f'  <url><loc>{loc("/rehber")}</loc><priority>0.7</priority></url>\n'
    for guide in get_all_guides():
        xml += f'  <url><loc>{loc("/rehber/" + quote(str(guide["slug"])))}</loc></url>\n'

    xml += '</urlset>'
    return Response(xml, mimetype="application/xml")

@app.route("/koleksiyonlar")
def collections_list():
    from db import get_all_collections
    collections = cached("collections_list", get_all_collections)
    icon_map = {
        "yazilim": "💻", "yazılım": "💻", "startup": "🚀", "girisim": "🚀",
        "sanat": "🎨", "sanatci": "🎨", "gorsel": "🎨", "tasarim": "🎨",
        "icerik": "📝", "uretici": "🎬", "video": "🎬",
        "pazarlama": "📣", "satis": "💰", "eticaret": "🛒",
        "kod": "⌨️", "gelistirici": "⌨️",
    }
    for c in collections:
        slug_low = c.get("slug", "").lower()
        c["icon"] = next((v for k, v in icon_map.items() if k in slug_low), "📦")
    return render_template("collections.html", collections=collections)

@app.route("/koleksiyon/<slug>")
def collection_detail(slug):
    from db import get_collection_by_slug
    col = get_collection_by_slug(slug)
    if not col:
        abort(404)
    return render_template("collection_detail.html", collection=col)

@app.route("/api/advisor", methods=["POST"])
def api_advisor():
    """Hibrit AI Danisman API'si"""
    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "Sorgu bos"}), 400
        
    # 1. Veritabanindan kelime-bazli arama ile aday havuzu bul (dogal dil cumlelerini de kapsar)
    results = search_products_advisor(query, limit=30)
    if not results:
        return jsonify({
            "message": "Maalesef bu konuyla ilgili veritabanımızda henüz bir araç bulunmuyor.",
            "tools": []
        })
        
    candidates = results[:15] # LLM'e daha genis bir aday havuzu sun, en iyi 15'i degerlendirsin
    candidate_text = "\\n".join([f"- {c['title_tr']}: {c['summary_tr']} (ID: {c['id']})" for c in candidates])
    
    prompt = f"""Kullanici asagidaki konuda bir yapay zeka araci ariyor:
"{query}"

Elimizde su araclar var:
{candidate_text}

Kullanicinin istegine en uygun olanlari secip, ona samimi bir "Yapay Zeka Danismani" gibi kisa bir yanit ver.
Yanitinda onerdigin aracin ismini ve "Neden" secmesi gerektigini 1-2 cumleyle acikla.
JSON formatinda don. Format:
{{
  "message": "Danismanin genel mesaji (giris cumlesi)",
  "recommended_ids": [1, 5, 2] // Onerdigin araclarin integer ID'leri
}}
"""

    GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
    fallback_response = {
        "message": "İşte bulduğum en iyi araçlar:",
        "tools": candidates
    }
    if not GROQ_API_KEY:
        logger.warning("GROQ_API_KEY tanimli degil, fallback sonuc donduruluyor.")
        return jsonify(fallback_response)

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "response_format": {"type": "json_object"}
    }

    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers, json=payload, timeout=10
        )
        resp.raise_for_status()
        result = resp.json()
        content = json.loads(result["choices"][0]["message"]["content"])
    except requests.Timeout:
        logger.warning("Groq API zaman asimina ugradi (query=%r).", query)
        return jsonify(fallback_response)
    except requests.RequestException as e:
        logger.error("Groq API istegi basarisiz (query=%r): %s", query, e)
        return jsonify(fallback_response)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        logger.error("Groq yaniti parse edilemedi (query=%r): %s", query, e)
        return jsonify(fallback_response)

    recommended_ids = content.get("recommended_ids", [])
    final_tools = [c for c in candidates if c["id"] in recommended_ids]
    if not final_tools:
        final_tools = candidates  # AI hata yaparsa fallback

    return jsonify({
        "message": content.get("message", "İşte sizin için seçtiğim araçlar:"),
        "tools": final_tools
    })



@app.route("/favicon.ico")
def favicon_root():
    """Tarayicilar <link> tag'inden bagimsiz olarak kokten /favicon.ico ister."""
    return app.send_static_file("favicon.ico")


@app.route("/d4c153c71d2d2321087ed549ff32eb7c.txt")
def indexnow_key():
    """IndexNow protokolu (Bing/Yandex) icin dogrulama anahtari - kokten erisilebilir olmali.
    Bkz. ping_search_engines.py - yeni/guncellenen sayfalari arama motorlarina anlik bildirir."""
    return app.send_static_file("d4c153c71d2d2321087ed549ff32eb7c.txt")


@app.route("/robots.txt")
def robots():
    base = "https://" + request.host
    txt = f"""User-agent: *
Allow: /
Sitemap: {base}/sitemap.xml
"""
    return Response(txt, mimetype="text/plain")


@app.route("/ads.txt")
def ads_txt():
    pub_id = os.getenv("ADSENSE_PUBLISHER_ID", "").strip()
    if not pub_id:
        abort(404)
    # Ensure it starts with pub- instead of ca-pub- for the ads.txt entry
    clean_pub_id = pub_id.replace("ca-", "")
    content = f"google.com, {clean_pub_id}, DIRECT, f08c47fec0942fa0\n"
    return Response(content, mimetype="text/plain")


@app.route("/googlef4ed50b2ea173e10.html")
def google_site_verification():
    return Response("google-site-verification: googlef4ed50b2ea173e10.html", mimetype="text/html")


@app.route("/admin")
def admin():
    token = request.args.get("token", "")
    expected = os.getenv("ADMIN_TOKEN", "")
    if not expected or token != expected:
        abort(404)  # 401 yerine 404 -> panelin varligini gizler
    stats = get_admin_stats()
    visits = get_visit_stats()
    subscribers = get_all_subscribers()
    
    # Filtre Parametreleri
    days = request.args.get("days", 30, type=int)
    country = request.args.get("country", "All").strip()
    device = request.args.get("device", "All").strip()
    
    # Yeni analitik sorgularını çek
    from db import (
        get_top_clicked_tools_stats,
        get_category_clicks_stats,
        get_search_queries_stats,
        get_zero_click_tools_stats,
        get_orphan_opportunity_stats,
        get_referrer_distribution,
        get_entry_exit_matrix,
        get_multi_click_sessions,
        get_recent_user_journeys,
        get_average_time_to_first_click,
        get_content_os_dashboard
    )
    
    # Global/Eski filtreler (varsayılan 30 gün)
    top_clicked = get_top_clicked_tools_stats(days=days)
    category_clicks = get_category_clicks_stats(days=days)
    search_queries = get_search_queries_stats(days=days)
    zero_clicks = get_zero_click_tools_stats(days=90)
    orphans = get_orphan_opportunity_stats(days=days, limit=10)
    
    # Yeni Sprint 2 Analitikleri
    ref_dist = get_referrer_distribution(days=days, country=country, device=device)
    entry_exit = get_entry_exit_matrix(days=days, country=country, device=device)
    multi_clicks = get_multi_click_sessions(days=days, country=country, device=device)
    recent_journeys = get_recent_user_journeys(days=days, country=country, device=device, limit=50)
    avg_time = get_average_time_to_first_click(days=days, country=country, device=device)
    
    # Gelir simülatörü ayarları (GET parametreleri ile oynanabilir)
    conv_rate = request.args.get("conv", 2.0, type=float)
    avg_comm = request.args.get("comm", 18.0, type=float)
    
    # Toplam tıklama sayısı (Bugün)
    from datetime import date
    from db import get_daily_clicks_count
    today_str = date.today().isoformat()
    today_clicks = get_daily_clicks_count(today_str)
    
    # Content OS Data
    content_os = get_content_os_dashboard()
    
    return render_template(
        "admin.html", 
        stats=stats, 
        visits=visits, 
        subscribers=subscribers, 
        content_os=content_os,
        admin_token=token,
        top_clicked=top_clicked,
        category_clicks=category_clicks,
        search_queries=search_queries,
        zero_clicks=zero_clicks,
        orphans=orphans,
        ref_dist=ref_dist,
        entry_exit=entry_exit,
        multi_clicks=multi_clicks,
        recent_journeys=recent_journeys,
        avg_time=avg_time,
        conv_rate=conv_rate,
        avg_comm=avg_comm,
        today_clicks=today_clicks,
        filter_days=days,
        filter_country=country,
        filter_device=device
    )


@app.route("/go/<slug>")
def outbound_redirect(slug):
    from flask import redirect
    product = get_product_by_slug(slug)
    if not product:
        abort(404)
        
    ua = request.headers.get("User-Agent", "")
    
    # 1. Bot Filtreleme
    if is_bot(ua):
        dest_url = (product.get("affiliate_url") or "").strip() or product.get("website", "")
        if not dest_url.startswith(("http://", "https://")):
            dest_url = "https://" + dest_url
        return redirect(dest_url)
        
    # 2. Parametreleri Normalize Et
    dest_type = request.args.get("type", "website").strip().lower()
    valid_types = {"website", "affiliate", "github", "pricing", "docs", "discord", "download", "demo", "youtube", "api"}
    if dest_type not in valid_types:
        dest_type = "website"
        
    referrer = request.args.get("ref", "external").strip().lower()
    valid_refs = {"home", "product", "guide", "comparison", "collection", "category", "search", "newsletter", "trending", "admin", "external"}
    if referrer not in valid_refs:
        referrer = "external"
        
    raw_query = request.args.get("q", "").strip()
    import re
    search_query = re.sub(r"\s+", " ", raw_query.lower()) if raw_query else None
    
    # 3. Country & Device Normalization
    country = request.headers.get("X-Vercel-IP-Country", "Unknown").strip().upper()
    device = parse_device(ua)
    
    # 4. Kaydet
    try:
        session_id = request.cookies.get("tg_session")
        session_started_at = request.cookies.get("tg_session_started")
        record_outbound_click_event(
            session_id=session_id,
            product_id=product["id"],
            dest_type=dest_type,
            referrer=referrer,
            search_query=search_query,
            country=country,
            device=device,
            session_started_at=session_started_at
        )
    except Exception as e:
        logger.error(f"Failed to record outbound click: {e}")
        
    # 6. Yönlendir
    dest_url = (product.get("affiliate_url") or "").strip() or product.get("website", "")
        
    if not dest_url.startswith(("http://", "https://")):
        dest_url = "https://" + dest_url
        
    return redirect(dest_url)


@app.route("/admin/export/clicks")
def export_clicks():
    token = request.args.get("token", "")
    expected = os.getenv("ADMIN_TOKEN", "")
    if not expected or token != expected:
        abort(404)
        
    from db import get_raw_click_events_for_csv
    events = get_raw_click_events_for_csv(days=30)
    
    import csv
    import io
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow([
        "event_uuid", "session_id", "product_name", "product_slug",
        "clicked_at", "destination_type", "referrer", "search_query", "country", "device"
    ])
    
    for e in events:
        writer.writerow([
            e.get("event_uuid"),
            e.get("session_id"),
            e.get("product_name"),
            e.get("product_slug"),
            e.get("clicked_at"),
            e.get("destination_type"),
            e.get("referrer"),
            e.get("search_query"),
            e.get("country"),
            e.get("device")
        ])
        
    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=outbound_clicks_last_30_days.csv"
    return response


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=True)
