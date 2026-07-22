import os
import json
import re
import time
from dotenv import load_dotenv
from generate_content import _generate_with_fallback
from quality_gate import check_guide

load_dotenv()

_SUSPICIOUS_WORDS = ["thus", "however", "mejores", "the ", " and ", "que ", "para ", "with ", "para el"]


def call_llm(prompt: str, temperature: float = 0.55, max_tokens: int = 2048) -> dict:
    """Groq -> NVIDIA NIM -> Gemini sirasiyla dener (generate_content.py'deki paylasilan zincir)."""
    return _generate_with_fallback(
        prompt,
        groq_payload_extra={"temperature": temperature, "response_format": {"type": "json_object"}},
        max_tokens=max_tokens,
    )


def generate_section(prompt: str, label: str, max_tokens: int = 2048) -> dict:
    """Bir bolumu uretir, yabanci kelime sizintisi varsa bir kez daha dener."""
    data = call_llm(prompt, max_tokens=max_tokens)
    full_text = json.dumps(data, ensure_ascii=False).lower()
    if any(w in full_text for w in _SUSPICIOUS_WORDS):
        print(f"    ({label}: yabanci kelime sizintisi, tekrar deneniyor...)")
        data = call_llm(prompt, temperature=0.45, max_tokens=max_tokens)
    return data


_COMMON_RULES = """
KURALLAR (cok onemli, kesinlikle uy):
- SADECE ve SADECE Turkce yaz. Baska hicbir dilden tek kelime bile kullanma.
- Sadece asagida verilen araclardan bahset, baska arac ismi UYDURMA veya ekleme.
- Fiyat bilgisi olarak SADECE verilen bilgiyi kullan, uydurma rakam verme.
- Dogal, akici, samimi ama profesyonel bir uslup kullan (reklam gibi degil, tekrar eden cumleler kurma).
- KISA VE OZ YAZ: kullanici bu sayfayi OKUMAYACAK, TARAYACAK. Uzun paragraf yerine kisa,
  carpici cumleler kullan. Belirtilen kelime sayisi hedefleri UST SINIRDIR, hedefin altinda
  kalman sorun degil - onemli olan her cumlenin gercekten yeni bilgi tasimasi, doldurma
  cumle KESINLIKLE yazma.
"""


def build_intro_prompt(topic_title: str, tools_desc: str) -> str:
    return f"""Sen deneyimli bir Turkce teknoloji editorusun. Asagidaki konu icin bir SEO
rehberinin GIRIS bolumlerini yaz.

KONU: {topic_title}

Bahsedilecek araclar (baglam icin):
{tools_desc}
{_COMMON_RULES}

Su JSON formatinda cevap ver (baska hicbir sey yazma):
{{
  "meta_description": "Google sonuclarinda gorunecek 150-160 karakterlik ozet",
  "excerpt": "Sayfa basinda gorunecek 1-2 cumlelik giris ozeti",
  "hizli_ozet": "TAM OLARAK 2-3 cumlelik DOGRUDAN cevap. Kullanici sayfaya gelir gelmez en onemli tavsiyeyi hemen alsin (hangi arac/yaklasim one cikiyor, neden). Google'in AI/featured snippet sonuclarina uygun, oz ve net olsun. ONEMLI: 'Kisa cevap:' ifadesiyle BASLAMA, bu ifade zaten otomatik ekleniyor - direkt cevapla basla.",
  "ogrenecekleriniz": ["Bu rehberde ogrenilecek 4 kisa madde (her biri 4-8 kelime, fiil ile baslasin, ornek: 'Hangi aracin size uygun oldugunu' gibi)", "madde 2", "madde 3", "madde 4"],
  "giris": "EN FAZLA 60-80 kelimelik giris paragrafi. Okuyucunun sorununu/ihtiyacini tek cumlede tanimla, bu rehberde ne bulacagini kisaca soyle. Uzatma.",
  "neden_ai": ["Yapay zeka kullanmanin faydasi 1 - TEK CUMLE, somut (zaman/para/kalite)", "fayda 2 - tek cumle", "fayda 3 - tek cumle", "fayda 4 - tek cumle (3-4 madde, HER biri EN FAZLA 20 kelime)"]
}}
"""


def build_steps_prompt(topic_title: str, tools_desc: str) -> str:
    return f"""Sen deneyimli bir Turkce teknoloji editorusun. Asagidaki konu icin bir SEO
rehberinin "ADIM ADIM NASIL YAPILIR" bolumunu yaz.

KONU: {topic_title}

Bahsedilecek araclar (baglam icin, adimlarda genel gecer/arac-bagimsiz bir surec anlat):
{tools_desc}
{_COMMON_RULES}

Su JSON formatinda cevap ver (baska hicbir sey yazma):
{{
  "adimlar_baslik": "Bu bolumun kisa (1 cumle) giris cumlesi",
  "adimlar": ["TEK BIR STRING icinde 'Kisa Baslik: Ayrintili aciklama (EN FAZLA 30-40 kelime)' formatinda - basligi ve aciklamayi AYRI array elemanlari yapma, TEK string olarak birlestir", "Adim 2 - ayni format, TEK string", "Adim 3 - ayni format, TEK string", "Adim 4 - ayni format, TEK string (4-5 adim arasi olsun, HER adim kendi icinde baslik+aciklama birlesik TEK string olmali, KISA tut)"]
}}
"""


def build_tools_prompt(topic_title: str, tools: list) -> str:
    tools_list_text = "\n".join([
        f"{i+1}. {t['name']} — Kimin icin: {t.get('best_for', '')} — Fiyat: {t.get('pricing', 'Bilinmiyor')}"
        for i, t in enumerate(tools)
    ])
    return f"""Sen deneyimli bir Turkce teknoloji editorusun. Asagidaki konu icin bir SEO
rehberinin "EN IYI ARAÇLAR" bolumunu yaz. Her arac icin AYRI ve KISA bir tanitim yaz.

KONU: {topic_title}

Tanitilacak araclar (bu SIRAYLA, hepsi icin yaz, baska arac ekleme):
{tools_list_text}
{_COMMON_RULES}

Her arac aciklamasi EN FAZLA 50-70 kelime olsun: ne ise yaradigini ve one cikan TEK
ozelligini soyle, uzun anlatima girme - kullanici zaten "Detayli incelemeyi oku" linkinden
tam sayfaya gidebilir, burasi sadece hizli tanitim.

Su JSON formatinda cevap ver (baska hicbir sey yazma, tam olarak {len(tools)} tane eleman olsun, SIRAYI KORU):
{{
  "en_iyi_araclar": [
    {{"isim": "arac ismi (yukaridaki listeden BIREBIR ayni)", "aciklama": "EN FAZLA 50-70 kelimelik kisa aciklama"}}
  ]
}}
"""


def build_alt_mistakes_prompt(topic_title: str, tools_desc: str) -> str:
    return f"""Sen deneyimli bir Turkce teknoloji editorusun. Asagidaki konu icin bir SEO
rehberinin "UCRETSIZ ALTERNATIFLER" ve "SIK YAPILAN HATALAR" bolumlerini yaz.

KONU: {topic_title}

Baglam (bahsedilen araclar):
{tools_desc}
{_COMMON_RULES}

Su JSON formatinda cevap ver (baska hicbir sey yazma):
{{
  "ucretsiz_alternatif_notu": "EN FAZLA 70-90 kelimelik, ucretsiz/dusuk butceli secenekler hakkinda kisa bir not. Hangi araclarin ucretsiz katmani oldugunu kisaca soyle.",
  "hatalar": ["Sik yapilan hata 1 - EN FAZLA 20-30 kelime aciklamali", "Hata 2 - 20-30 kelime", "Hata 3 - 20-30 kelime", "Hata 4 - 20-30 kelime (3-4 hata arasi, kisa tut)"]
}}
"""


def build_faq_prompt(topic_title: str, tools_desc: str) -> str:
    return f"""Sen deneyimli bir Turkce teknoloji editorusun. Asagidaki konu icin bir SEO
rehberinin "SIK SORULAN SORULAR" bolumunu yaz. Sorular gercekten insanlarin Google'a
yazacagi turden, arama niyetine uygun olsun.

KONU: {topic_title}

Baglam (bahsedilen araclar):
{tools_desc}
{_COMMON_RULES}
- 4 SORU BIRBIRINDEN TAMAMEN FARKLI olmali, hicbiri ayni seyi baska kelimelerle sormamali
  (orn. "hangi araclari kullanabilirim" ve "en iyi araclar hangileri" gibi benzer sorulari
  TEKRAR ETME, her soru farkli bir acidan yaklassin: fiyat, guvenlik, baslangic seviyesi,
  profesyonel kullanim, ozel bir senaryo gibi).

Su JSON formatinda cevap ver (baska hicbir sey yazma, tam olarak 4 soru-cevap):
{{
  "sss": [
    {{"soru": "Soru 1 (dogal, Google'da aranacak turden)", "cevap": "TAM OLARAK 134-167 kelimelik, kendi basina eksiksiz bir cevap - AI arama motorlarinin (ChatGPT, Perplexity, Google AI Overviews) dogrudan alintilayabilecegi, baglam gerektirmeyen tam bir yanit olsun"}},
    {{"soru": "Soru 2", "cevap": "TAM OLARAK 134-167 kelime, kendi basina eksiksiz"}},
    {{"soru": "Soru 3", "cevap": "TAM OLARAK 134-167 kelime, kendi basina eksiksiz"}},
    {{"soru": "Soru 4", "cevap": "TAM OLARAK 134-167 kelime, kendi basina eksiksiz"}}
  ]
}}
"""


def _tools_desc_text(tools: list) -> str:
    return "\n".join([
        f"- {t['name']}: {t.get('best_for', '')} (Fiyat: {t.get('pricing', 'Bilinmiyor')})"
        for t in tools
    ])


def _pricing_badge_html(pricing_text: str) -> str:
    p = (pricing_text or "").lower()
    if "ücretsiz" in p and "ücretli" not in p and "$" not in p and "/ay" not in p:
        return "<span class='badge badge-free'>🆓 Ücretsiz</span>"
    if "ücretsiz" in p:
        return "<span class='badge badge-freemium'>💎 Freemium</span>"
    return "<span class='badge badge-paid'>💰 Ücretli</span>"


def _render_tool_card(name: str, aciklama: str, tool_meta: dict, tool_extra: dict) -> str:
    extra = (tool_extra or {}).get(name, {})
    slug = extra.get("slug")
    thumbnail = extra.get("thumbnail")
    pricing = tool_meta.get("pricing", "") if tool_meta else ""
    best_for = tool_meta.get("best_for", "") if tool_meta else ""

    icon_html = (
        f"<img src='{thumbnail}' alt='{name}' style='width:44px;height:44px;border-radius:10px;object-fit:cover;'>"
        if thumbnail else
        "<div style='width:44px;height:44px;border-radius:10px;background:var(--tag-bg);"
        "display:flex;align-items:center;justify-content:center;font-size:1.3rem;'>🛠️</div>"
    )
    name_html = (
        f"<a href='/urun/{slug}' style='color:var(--text);text-decoration:none;'>{name}</a>"
        if slug else name
    )

    return f"""
<div class="guide-tool-card">
  <div class="guide-tool-card-head">
    {icon_html}
    <div class="guide-tool-card-titles">
      <h3 class="guide-tool-card-name">{name_html}</h3>
      {f"<p class='guide-tool-card-bestfor'>{best_for}</p>" if best_for else ""}
    </div>
    {_pricing_badge_html(pricing)}
  </div>
  <p class="guide-tool-card-desc">{aciklama}</p>
  {f"<a href='/urun/{slug}' class='btn btn-sm'>Detaylı incelemeyi oku →</a>" if slug else ""}
</div>
"""


def generate_guide_content(topic_title: str, tools: list, tool_extra: dict = None) -> dict:
    """Tum bolumleri ayri Groq cagrilariyla uretir, birlestirip tek bir sonuc dondurur."""
    tools_desc = _tools_desc_text(tools)

    print("    (bolum 1/5: giris + neden-ai)")
    intro = generate_section(build_intro_prompt(topic_title, tools_desc), "giris")
    time.sleep(1)

    print("    (bolum 2/5: adim adim)")
    steps = generate_section(build_steps_prompt(topic_title, tools_desc), "adimlar")
    time.sleep(1)

    print("    (bolum 3/5: en iyi araclar)")
    tools_section = generate_section(build_tools_prompt(topic_title, tools), "araclar")
    time.sleep(1)

    print("    (bolum 4/5: ucretsiz alternatif + hatalar)")
    alt_mistakes = generate_section(build_alt_mistakes_prompt(topic_title, tools_desc), "alternatif")
    time.sleep(1)

    print("    (bolum 5/5: SSS)")
    faq = generate_section(build_faq_prompt(topic_title, tools_desc), "sss")
    time.sleep(1)

    html_parts = []
    if intro.get("hizli_ozet"):
        html_parts.append(f"<div class='guide-quick-answer'><strong>⚡ Kısa cevap:</strong> {intro['hizli_ozet']}</div>")
    if intro.get("ogrenecekleriniz"):
        html_parts.append("<div class='guide-learn-box'><div class='guide-learn-title'>📋 Bu rehberde öğrenecekleriniz</div><ul>")
        for madde in intro["ogrenecekleriniz"]:
            html_parts.append(f"<li>{madde}</li>")
        html_parts.append("</ul></div>")
    html_parts.append(f"<p>{intro['giris']}</p>")
    html_parts.append("<h2>Neden Yapay Zeka Kullanmalısınız?</h2>")
    html_parts.append("<ul class='guide-benefits'>")
    for fayda in intro.get("neden_ai", []):
        html_parts.append(f"<li>{fayda}</li>")
    html_parts.append("</ul>")

    html_parts.append(f"<h2>{steps.get('adimlar_baslik', 'Adım Adım Nasıl Yapılır?')}</h2>")
    html_parts.append("<ol class='guide-steps'>")
    for adim in steps["adimlar"]:
        html_parts.append(f"<li>{adim}</li>")
    html_parts.append("</ol>")

    html_parts.append("<h2>En İyi Araçlar</h2>")
    tools_by_name = {t["name"]: t for t in tools}
    for t in tools_section["en_iyi_araclar"]:
        tool_meta = tools_by_name.get(t["isim"])
        html_parts.append(_render_tool_card(t["isim"], t["aciklama"], tool_meta, tool_extra))

    html_parts.append("<h2>Ücretsiz Alternatifler</h2>")
    html_parts.append(f"<p>{alt_mistakes['ucretsiz_alternatif_notu']}</p>")

    html_parts.append("<h2>Sık Yapılan Hatalar</h2>")
    html_parts.append("<ul class='guide-mistakes'>")
    for h in alt_mistakes["hatalar"]:
        html_parts.append(f"<li>{h}</li>")
    html_parts.append("</ul>")

    html_parts.append("<h2>Sık Sorulan Sorular</h2>")
    for qa in faq["sss"]:
        html_parts.append(f"<h3>{qa['soru']}</h3>")
        html_parts.append(f"<p>{qa['cevap']}</p>")

    content_html = "\n".join(html_parts)
    word_count = len(content_html.split())

    return {
        "meta_description": intro["meta_description"],
        "excerpt": intro["excerpt"],
        "content_html": content_html,
        "word_count": word_count,
        "faq_qa": faq["sss"],
    }


GUIDES = [
    {
        "slug": "ai-ile-logo-nasil-olusturulur",
        "title": "AI ile Logo Nasıl Oluşturulur? (2026 Rehberi)",
        "comparison_slug": "ai-logo-tasarim-araclari",
        "related_topic": "Tasarim",
    },
    {
        "slug": "ai-ile-sunum-hazirlama-rehberi",
        "title": "AI ile Sunum Hazırlama Rehberi (2026)",
        "comparison_slug": "ai-sunum-araclari",
        "related_topic": "Productivity",
    },
    {
        "slug": "ai-seslendirme-nasil-yapilir",
        "title": "AI Seslendirme Nasıl Yapılır? (2026 Rehberi)",
        "comparison_slug": "en-iyi-ai-ses-ve-seslendirme-araclari",
        "related_topic": "",
    },
    {
        "slug": "ai-video-olusturma-rehberi",
        "title": "AI ile Video Oluşturma Rehberi (2026)",
        "comparison_slug": "video-ureten-ai-araclari",
        "related_topic": "Video",
    },
    {
        "slug": "en-iyi-ucretsiz-ai-araclari",
        "title": "En İyi Ücretsiz AI Araçları (2026)",
        "comparison_slug": None,
        "related_topic": "",
        "manual_tools": [
            {"name": "Cito", "best_for": "236 milyon akademik makale arasında ücretsiz araştırma/arama yapmak isteyenler", "pricing": "Ücretsiz"},
            {"name": "Scribble Party", "best_for": "Öğretmenler ve içerik üreticileri için yerel/offline çalışan araçlar arayanlar", "pricing": "Ücretsiz"},
            {"name": "Yapper Leaderboard", "best_for": "Twitter'da öne çıkan startup ve kullanıcıları takip etmek isteyenler", "pricing": "Ücretsiz"},
            {"name": "dot.", "best_for": "Herhangi bir şey için hızlı, ücretsiz geri bildirim toplamak isteyenler", "pricing": "Ücretsiz"},
            {"name": "Amami", "best_for": "Site trafiğini ve ziyaretçi sayısını kolayca, ücretsiz takip etmek isteyenler", "pricing": "Ücretsiz"},
        ],
        "related_comparisons": [],
    },
]


def existing_guide_comparison_slugs() -> set:
    """Zaten bir rehberi olan comparison_slug'lari dondurur (tekrar uretmemek icin)."""
    from db import get_all_guides
    result = set()
    for g in get_all_guides():
        for s in (g.get("related_comparison_slugs") or "").split(","):
            s = s.strip()
            if s:
                result.add(s)
    return result


def discover_candidate_guides(max_candidates: int = 3) -> list:
    """
    Henuz hic rehberi olmayan karsilastirmalari bulup otomatik guide_cfg listesi uretir.
    generate_guide.py suana kadar sabit GUIDES listesiyle calisiyordu (elle yonetiliyordu);
    bu fonksiyon auto_generate_comparisons.py'deki CANDIDATE_TOPICS mantiginin rehber
    tarafindaki karsiligi - karsilastirma sayisi buyudukce rehberler de otomatik yetissin diye.
    """
    from db import get_all_comparisons

    covered = existing_guide_comparison_slugs()
    manual_slugs = {g["slug"] for g in GUIDES}
    candidates = []
    for comp in get_all_comparisons():
        if comp["slug"] in covered:
            continue
        # comparison_detail'de zaten "kart >= 3" kurali var (auto_generate_comparisons MIN_PRODUCTS=5),
        # bu yuzden burada ayrica bir minimum kontrolu tekrar yapmiyoruz.
        guide_title = comp["title"]
        if "(20" in guide_title:  # "(2026)" gibi bir yil eki varsa rehber basligina tekrar ekleme
            guide_title = re.sub(r"\s*\(20\d{2}\)", "", guide_title)
        candidates.append({
            "slug": f"{comp['slug']}-rehberi",
            "title": f"{guide_title}: Hangisini Seçmelisiniz? (Rehber)",
            "comparison_slug": comp["slug"],
            "related_topic": "",
        })
        if len(candidates) >= max_candidates:
            break
    return candidates


def build_guide_cfg_for_product(product_id: int):
    """
    Tek bir urun icin (Content OS'un content_tasks kuyrugundan gelen GUIDE gorevleri icin)
    'X ve Alternatifleri' rehber konfigurasyonu kurar - discover_orphan_guides()'in ic
    mantiginin tek-urunluk, disaridan cagrilabilir hali (kod tekrarini onlemek icin
    ikisi de bu fonksiyonu kullanir).
    Donen: guide_cfg dict, veya yeterli benzer urun yoksa None.
    """
    from db import get_connection, init_db
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT id, original_name, slug, topics, summary_tr, pricing_type FROM products WHERE id = ?",
        (product_id,)
    ).fetchone()
    if not row:
        conn.close()
        return None
    product = dict(row)

    topics = (product["topics"] or "").split(",")
    first_topic = topics[0].strip() if topics else ""
    if not first_topic:
        conn.close()
        return None

    similar = conn.execute(
        "SELECT original_name, summary_tr, pricing_type FROM products WHERE topics LIKE ? AND id != ? ORDER BY votes DESC LIMIT 4",
        (f"%{first_topic}%", product["id"])
    ).fetchall()
    conn.close()

    if len(similar) < 2:
        return None

    manual_tools = [{
        "name": product["original_name"],
        "best_for": (product["summary_tr"] or "")[:100],
        "pricing": product["pricing_type"] or "Bilinmiyor",
    }]
    for s in similar:
        s = dict(s)
        manual_tools.append({
            "name": s["original_name"],
            "best_for": (s["summary_tr"] or "")[:100],
            "pricing": s["pricing_type"] or "Bilinmiyor",
        })

    return {
        "slug": f"{product['slug']}-rehberi",
        "title": f"{product['original_name']} ve Alternatifleri: Hangisini Seçmelisiniz? (2026 Rehberi)",
        "comparison_slug": None,
        "related_topic": first_topic,
        "manual_tools": manual_tools,
        "related_comparisons": [],
    }


def discover_orphan_guides(max_candidates: int = 2, min_clicks: int = 2):
    """
    Admin paneldeki 'Orphan Firsat Raporu'nun otomasyonu.
    En cok tiklanan ama hic rehberi olmayan araclari bulur ve
    onlar icin otomatik rehber uretim konfigurasyonu dondurur.
    
    Mantik:
    1. outbound_click_events tablosundan en cok tiklanan urunleri cek
    2. Zaten bir rehberde gecen urunleri filtrele
    3. Kalan urunlerin ayni kategorisindeki (topic) diger urunleri bul
    4. Bu urunlerle bir rehber konfigurasyonu olustur
    """
    from db import get_connection, init_db
    from datetime import datetime, timedelta
    init_db()
    conn = get_connection()
    
    # 1. Son 30 gundeki en cok tiklanan urunler
    now = datetime.utcnow()
    t_start = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    top_clicked = conn.execute("""
        SELECT p.id, p.original_name, p.slug, p.topics, p.summary_tr,
               p.pricing_type, COUNT(e.id) as clicks
        FROM products p
        JOIN outbound_click_events e ON p.id = e.product_id
        WHERE e.clicked_at >= ?
        GROUP BY p.id, p.original_name, p.slug, p.topics, p.summary_tr, p.pricing_type
        HAVING COUNT(e.id) >= ?
        ORDER BY COUNT(e.id) DESC
        LIMIT 20
    """, (t_start, min_clicks)).fetchall()
    
    # 2. Rehberlerde zaten gecen slug'lari bul
    guides_rows = conn.execute("SELECT related_tool_slugs FROM guides").fetchall()
    covered_slugs = set()
    for g in guides_rows:
        for s in (g["related_tool_slugs"] or "").split(","):
            s = s.strip()
            if s:
                covered_slugs.add(s)
    
    # 3. Orphan olanlari filtrele
    candidates = []
    for row in top_clicked:
        product = dict(row)
        if product["slug"] in covered_slugs:
            continue
        
        # Ayni topic'teki diger urunleri bul (rehber icin en az 3 arac lazim)
        topics = (product["topics"] or "").split(",")
        first_topic = topics[0].strip() if topics else ""
        if not first_topic:
            continue
        
        similar = conn.execute(
            "SELECT original_name, summary_tr, pricing_type FROM products WHERE topics LIKE ? AND id != ? ORDER BY votes DESC LIMIT 4",
            (f"%{first_topic}%", product["id"])
        ).fetchall()
        
        if len(similar) < 2:  # En az 3 arac (1 ana + 2 benzer) olmali
            continue
        
        # Rehber konfigurasyonu olustur
        manual_tools = [
            {
                "name": product["original_name"],
                "best_for": (product["summary_tr"] or "")[:100],
                "pricing": product["pricing_type"] or "Bilinmiyor",
            }
        ]
        for s in similar:
            s = dict(s)
            manual_tools.append({
                "name": s["original_name"],
                "best_for": (s["summary_tr"] or "")[:100],
                "pricing": s["pricing_type"] or "Bilinmiyor",
            })
        
        from db import slugify
        guide_slug = f"{product['slug']}-rehberi"
        
        candidates.append({
            "slug": guide_slug,
            "title": f"{product['original_name']} ve Alternatifleri: Hangisini Secmelisiniz? (2026 Rehberi)",
            "comparison_slug": None,
            "related_topic": first_topic,
            "manual_tools": manual_tools,
            "related_comparisons": [],
            "_source": "orphan",
            "_clicks": product["clicks"],
        })
        
        if len(candidates) >= max_candidates:
            break
    
    conn.close()
    
    if candidates:
        print(f"Orphan Firsat Raporu: {len(candidates)} aday rehber bulundu:")
        for c in candidates:
            print(f"  - {c['title']} ({c['_clicks']} tiklama)")
    else:
        print("Orphan Firsat Raporu: Tum cok tiklanan araclarin zaten bir rehberi var.")
    
    return candidates


def run_scheduler(max_new: int = 2):
    """
    Guide Scheduler: iki kaynaktan aday rehber bulur ve uretir:
    1. Karsilastirma listelerinden (comparison-based)
    2. Orphan Firsat Raporundan (click-based) - admin paneldeki veriye dayanir
    
    Her rehber kalite kapisindan (quality_gate.check_guide) gecmeden yayinlanmaz.
    Haftalik workflow'dan cagrilir (bkz. weekly-content-generation.yml).
    """
    # Kaynak 1: Karsilastirma listelerinden aday bul
    comp_candidates = discover_candidate_guides(max_candidates=max_new)
    
    # Kaynak 2: Orphan (cok tiklanan ama rehberi olmayan) araclardan aday bul
    orphan_candidates = discover_orphan_guides(max_candidates=max_new, min_clicks=2)
    
    # Birlestir (once orphan - cunku tiklama verisiyle kanitlanmis talep)
    all_candidates = orphan_candidates + comp_candidates
    
    # Toplam limiti asma
    all_candidates = all_candidates[:max_new * 2]  # Her kaynaktan max_new kadar
    
    if not all_candidates:
        print("Yeni rehber adayi yok - tum karsilastirmalarin ve cok tiklanan araclarin zaten bir rehberi var.")
        return 0, 0, []

    created, rejected = 0, 0
    rejection_report = []
    for cfg in all_candidates:
        source = cfg.get("_source", "comparison")
        print(f"\n[Kaynak: {source}] {cfg['title']}")
        ok, problems = run_one(cfg, validate=True)
        if ok:
            created += 1
        else:
            rejected += 1
            rejection_report.append({"title": cfg["title"], "problems": problems})
        time.sleep(2)

    print(f"\nGuide Scheduler bitti. Olusturulan: {created}, Kalite kapisinda reddedilen: {rejected}")
    return created, rejected, rejection_report


def run_one(guide_cfg: dict, validate: bool = False):
    from db import init_db, save_guide, get_comparison_by_slug, get_connection, normalize_name

    init_db()
    slug = guide_cfg["slug"]
    title = guide_cfg["title"]
    print(f"[{slug}] üretiliyor...")

    if guide_cfg["comparison_slug"]:
        comp = get_comparison_by_slug(guide_cfg["comparison_slug"])
        if not comp:
            print(f"  !! HATA: comparison '{guide_cfg['comparison_slug']}' bulunamadi, atlaniyor.")
            return (False, ["comparison bulunamadi"]) if validate else None
        tools = comp["tools"]
        related_comparison_slugs = [guide_cfg["comparison_slug"]]
    else:
        tools = guide_cfg.get("manual_tools", [])
        related_comparison_slugs = guide_cfg.get("related_comparisons", [])

    # Kart gorunumu icin gercek urun verisini (slug, thumbnail) onceden cekiyoruz -
    # boylece "En Iyi Araclar" bolumu duz metin yerine gercek ikon+ic link iceren kart olur.
    related_tool_slugs = []
    tool_extra = {}
    conn = get_connection()
    for t in tools:
        row = conn.execute(
            "SELECT slug, thumbnail FROM products WHERE normalized_name = ?", (normalize_name(t["name"]),)
        ).fetchone()
        if row:
            row = dict(row)
            related_tool_slugs.append(row["slug"])
            tool_extra[t["name"]] = {"slug": row["slug"], "thumbnail": row.get("thumbnail")}
    conn.close()

    result = generate_guide_content(title, tools, tool_extra)
    print(f"  -> kelime sayisi: {result['word_count']}")

    if validate:
        ok, problems = check_guide(
            title=title,
            meta_description=result["meta_description"],
            content_html=result["content_html"],
            word_count=result["word_count"],
            related_tool_slugs=related_tool_slugs,
            source_tool_names=[t["name"] for t in tools],
        )
        if not ok:
            print(f"  !! KALITE KAPISI REDDETTI ({len(problems)} sorun):")
            for pr in problems:
                print(f"     - {pr}")
            return (False, problems)

    save_guide(
        slug=slug,
        title=title,
        meta_description=result["meta_description"],
        excerpt=result["excerpt"],
        content_html=result["content_html"],
        related_topic=guide_cfg.get("related_topic", ""),
        related_tool_slugs=related_tool_slugs,
        related_comparison_slugs=related_comparison_slugs,
        faq_json=result.get("faq_qa"),
    )
    print(f"  -> kaydedildi: /rehber/{slug}")
    return (True, []) if validate else None


if __name__ == "__main__":
    import sys
    if "--auto" in sys.argv:
        # Guide Scheduler: buyuyen karsilastirma listesine gore otomatik yeni rehber uretir.
        created, rejected, rejection_report = run_scheduler(max_new=2)
        gh_output = os.environ.get("GITHUB_OUTPUT")
        if gh_output:
            with open(gh_output, "a", encoding="utf-8") as f:
                f.write(f"guide_rejected_count={rejected}\n")
                if rejection_report:
                    lines = []
                    for r in rejection_report:
                        lines.append(f"### {r['title']}")
                        for pr in r["problems"]:
                            lines.append(f"- {pr}")
                    f.write("guide_rejection_report<<EOF\n")
                    f.write("\n".join(lines) + "\n")
                    f.write("EOF\n")
    elif len(sys.argv) > 1:
        target_slug = sys.argv[1]
        cfg = next((g for g in GUIDES if g["slug"] == target_slug), None)
        if not cfg:
            print(f"Rehber bulunamadi: {target_slug}")
        else:
            run_one(cfg)
    else:
        for g in GUIDES:
            if g["comparison_slug"] is None:
                print(f"[{g['slug']}] atlaniyor (manuel arac verisi gerekiyor, ayri calistirilacak)")
                continue
            run_one(g)
            time.sleep(2)

