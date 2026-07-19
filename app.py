import os
import json
import logging
import requests
from dotenv import load_dotenv
load_dotenv()  # local'de .env'i yukler; production'da (Vercel) zaten env var'lar hazir, zararsiz.
from flask import Flask, render_template, abort, request, jsonify, Response, g
from db import (
    init_db, get_all_products, get_product_by_slug,
    get_all_comparisons, get_comparison_by_slug,
    get_trending_products, get_recent_products,
    get_products_by_topic, search_products, search_products_advisor,
    get_all_topics, get_similar_products, get_top_products_by_period,
    subscribe_email,
    get_products_paginated, get_comparisons_for_product, get_collections_for_product,
    get_admin_stats,
)
import os
from rules_engine import derive_use_cases_and_personas

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("toolgundem")

app = Flask(__name__, static_folder="static", static_url_path="/static")
init_db()


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


def get_cta_url(product):
    """Affiliate linki varsa onu, yoksa resmi siteyi dondurur (kullanici fark etmez)."""
    return (product.get("affiliate_url") or "").strip() or product.get("website", "")


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
    """Tum template'lerde kullanilabilecek global degiskenler."""
    return {
        "topic_labels": TOPIC_LABELS,
        "topic_icons": TOPIC_ICONS,
        "get_topic_icon": get_topic_icon,
        "get_comparison_icon": get_comparison_icon,
        "get_cta_url": get_cta_url,
        "get_cta_label": get_cta_label,
        "turkce_tarih": turkce_tarih,
    }


@app.route("/")
def home():
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

    return render_template(
        "index.html",
        trending=trending,
        recent=recent,
        weekly_top=weekly_top,
        monthly_top=monthly_top,
        topics=topics,
        comparisons=comparisons,
        total_products=total_products,
        new_last_30d=new_last_30d,
        new_today=new_today,
        new_cutoff=three_days_ago,
        use_case_cta=USE_CASE_CTA,
    )


@app.route("/urun/<slug>")
def detail(slug):
    product = get_product_by_slug(slug)
    if not product:
        abort(404)
    similar = get_similar_products(product["id"], limit=4)
    related_comparisons = get_comparisons_for_product(product.get("normalized_name"))
    related_collections = get_collections_for_product(product.get("id"))
    tags = derive_use_cases_and_personas(product.get("topics", ""), product.get("tags", ""))
    return render_template(
        "detail.html", product=product, similar=similar,
        related_comparisons=related_comparisons,
        related_collections=related_collections,
        use_cases=tags["use_cases"], personas=tags["personas"],
    )


@app.route("/karsilastirma")
def comparisons_list():
    comparisons = get_all_comparisons()
    return render_template("comparisons.html", comparisons=comparisons)


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
    return render_template("comparison_detail.html", comparison=comparison)


@app.route("/kategori/<topic>")
def category(topic):
    products = get_products_by_topic(topic)
    fiyat = request.args.get("fiyat", "").strip()
    if fiyat:
        products = [p for p in products if p.get("pricing_type") == fiyat]
    label = TOPIC_LABELS.get(topic, topic)
    icon = TOPIC_ICONS.get(topic, "📁")
    all_topics = get_merged_topics()
    return render_template(
        "category.html",
        topic=topic,
        topic_label=label,
        topic_icon=icon,
        products=products,
        all_topics=all_topics,
    )


@app.route("/ara")
def search():
    query = request.args.get("q", "").strip()
    results = []
    if query:
        results = search_products(query)
    return render_template("search.html", query=query, results=results)


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
    products = get_all_products()
    comparisons = get_all_comparisons()
    topics = get_all_topics()
    from db import get_all_collections
    collections = get_all_collections()
    base = "https://" + request.host

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    # Home
    xml += f'  <url><loc>{base}/</loc><priority>1.0</priority></url>\n'
    # Products
    for p in products:
        xml += f'  <url><loc>{base}/urun/{p["slug"]}</loc></url>\n'
    # Comparisons
    xml += f'  <url><loc>{base}/karsilastirma</loc><priority>0.8</priority></url>\n'
    for c in comparisons:
        xml += f'  <url><loc>{base}/karsilastirma/{c["slug"]}</loc></url>\n'
    # Categories
    for topic, count in topics:
        xml += f'  <url><loc>{base}/kategori/{topic}</loc></url>\n'
    # Collections
    for col in collections:
        xml += f'  <url><loc>{base}/koleksiyon/{col["slug"]}</loc></url>\n'

    xml += '</urlset>'
    return Response(xml, mimetype="application/xml")

@app.route("/koleksiyonlar")
def collections_list():
    from db import get_all_collections
    collections = get_all_collections()
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


@app.route("/robots.txt")
def robots():
    base = "https://" + request.host
    txt = f"""User-agent: *
Allow: /
Sitemap: {base}/sitemap.xml
"""
    return Response(txt, mimetype="text/plain")


@app.route("/admin")
def admin():
    token = request.args.get("token", "")
    expected = os.getenv("ADMIN_TOKEN", "")
    if not expected or token != expected:
        abort(404)  # 401 yerine 404 -> panelin varligini gizler
    stats = get_admin_stats()
    return render_template("admin.html", stats=stats)


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=True)
