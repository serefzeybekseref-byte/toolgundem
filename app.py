import os
import json
import logging
import requests
from flask import Flask, render_template, abort, request, jsonify, Response
from db import (
    init_db, get_all_products, get_product_by_slug,
    get_all_comparisons, get_comparison_by_slug,
    get_trending_products, get_recent_products,
    get_products_by_topic, search_products,
    get_all_topics, get_similar_products,
    get_products_paginated,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("toolgundem")

app = Flask(__name__, static_folder="static", static_url_path="/static")
init_db()


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
}


@app.context_processor
def inject_globals():
    """Tum template'lerde kullanilabilecek global degiskenler."""
    return {
        "topic_labels": TOPIC_LABELS,
        "topic_icons": TOPIC_ICONS,
    }


@app.route("/")
def home():
    trending = get_trending_products(limit=6)
    recent = get_recent_products(limit=6)
    topics = get_all_topics()
    comparisons = get_all_comparisons()
    
    # Get total product count for the stats section
    from db import get_connection
    conn = get_connection()
    total_products = dict(conn.execute("SELECT COUNT(*) as cnt FROM products").fetchone())["cnt"]
    conn.close()
    
    return render_template(
        "index.html",
        trending=trending,
        recent=recent,
        topics=topics,
        comparisons=comparisons,
        total_products=total_products,
    )


@app.route("/urun/<slug>")
def detail(slug):
    product = get_product_by_slug(slug)
    if not product:
        abort(404)
    similar = get_similar_products(product["id"], limit=4)
    return render_template("detail.html", product=product, similar=similar)


@app.route("/karsilastirma")
def comparisons_list():
    comparisons = get_all_comparisons()
    return render_template("comparisons.html", comparisons=comparisons)


@app.route("/karsilastirma/<slug>")
def comparison_detail(slug):
    comparison = get_comparison_by_slug(slug)
    if not comparison:
        abort(404)
    return render_template("comparison_detail.html", comparison=comparison)


@app.route("/kategori/<topic>")
def category(topic):
    products = get_products_by_topic(topic)
    label = TOPIC_LABELS.get(topic, topic)
    icon = TOPIC_ICONS.get(topic, "📁")
    all_topics = get_all_topics()
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
    if topic:
        products = get_products_by_topic(topic)
        # Manual pagination
        start = (page - 1) * per_page
        end = start + per_page
        paginated = products[start:end]
        total = len(products)
    else:
        paginated, total = get_products_paginated(page, per_page)
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
    
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    # Home
    xml += '  <url><loc>https://toolgundem.com/</loc><priority>1.0</priority></url>\n'
    # Products
    for p in products:
        xml += f'  <url><loc>https://toolgundem.com/urun/{p["slug"]}</loc></url>\n'
    # Comparisons
    xml += '  <url><loc>https://toolgundem.com/karsilastirma</loc><priority>0.8</priority></url>\n'
    for c in comparisons:
        xml += f'  <url><loc>https://toolgundem.com/karsilastirma/{c["slug"]}</loc></url>\n'
    # Categories
    for topic, count in topics:
        xml += f'  <url><loc>https://toolgundem.com/kategori/{topic}</loc></url>\n'
    # Collections
    for col in collections:
        xml += f'  <url><loc>https://toolgundem.com/koleksiyon/{col["slug"]}</loc></url>\n'
        
    xml += '</urlset>'
    return Response(xml, mimetype="application/xml")

@app.route("/koleksiyonlar")
def collections_list():
    from db import get_all_collections
    collections = get_all_collections()
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
        
    # 1. Veritabanindan basit SQL aramasi ile adaylari bul (maksimum 10 arac)
    results = search_products(query)
    if not results:
        return jsonify({
            "message": "Maalesef bu konuyla ilgili veritabanımızda henüz bir araç bulunmuyor.",
            "tools": []
        })
        
    candidates = results[:5] # En iyi 5'i al
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



@app.route("/robots.txt")
def robots():
    txt = """User-agent: *
Allow: /
Sitemap: https://toolgundem.com/sitemap.xml
"""
    return Response(txt, mimetype="text/plain")


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=True)
