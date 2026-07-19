import os
import json
import time
from dotenv import load_dotenv
from generate_content import _generate_with_fallback

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
- Belirtilen kelime sayisi hedeflerine gercekten uy - kisa/yuzeysel yazma, her cumle yeni bilgi tasisin.
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
  "hizli_ozet": "TAM OLARAK 2-3 cumlelik DOGRUDAN cevap. Kullanici sayfaya gelir gelmez 'Kisa cevap: ...' diye baslayan bu kutuyu okuyup en onemli tavsiyeyi hemen alsin (hangi arac/yaklasim one cikiyor, neden). Google'in AI/featured snippet sonuclarina uygun, oz ve net olsun.",
  "giris": "TAM OLARAK 200-250 kelimelik giris paragrafi. Okuyucunun sorununu/ihtiyacini tanimla, bu rehberde ne bulacagini soyle.",
  "neden_ai": "TAM OLARAK 200-250 kelimelik 'Neden yapay zeka kullanmalisiniz' bolumu. Somut faydalar, zaman/para tasarrufu, geleneksel yontemle karsilastirma."
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
  "adimlar": ["TEK BIR STRING icinde 'Kisa Baslik: Ayrintili aciklama (70-100 kelime)' formatinda - basligi ve aciklamayi AYRI array elemanlari yapma, TEK string olarak birlestir", "Adim 2 - ayni format, TEK string", "Adim 3 - ayni format, TEK string", "Adim 4 - ayni format, TEK string", "Adim 5 - ayni format, TEK string (5-6 adim arasi olsun, HER adim kendi icinde baslik+aciklama birlesik TEK string olmali, array'de sadece 5-6 eleman olmali)"]
}}
"""


def build_tools_prompt(topic_title: str, tools: list) -> str:
    tools_list_text = "\n".join([
        f"{i+1}. {t['name']} — Kimin icin: {t.get('best_for', '')} — Fiyat: {t.get('pricing', 'Bilinmiyor')}"
        for i, t in enumerate(tools)
    ])
    return f"""Sen deneyimli bir Turkce teknoloji editorusun. Asagidaki konu icin bir SEO
rehberinin "EN IYI ARAÇLAR" bolumunu yaz. Her arac icin AYRI ve DETAYLI bir tanitim yaz.

KONU: {topic_title}

Tanitilacak araclar (bu SIRAYLA, hepsi icin yaz, baska arac ekleme):
{tools_list_text}
{_COMMON_RULES}

Her arac aciklamasi TAM OLARAK 120-160 kelime olsun: ne ise yarar, one cikan ozelligi,
kimler icin ideal, fiyati (verilen bilgiyi kullanarak) ve kucuk bir kullanim ipucu icersin.

Su JSON formatinda cevap ver (baska hicbir sey yazma, tam olarak {len(tools)} tane eleman olsun, SIRAYI KORU):
{{
  "en_iyi_araclar": [
    {{"isim": "arac ismi (yukaridaki listeden BIREBIR ayni)", "aciklama": "120-160 kelimelik detayli aciklama"}}
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
  "ucretsiz_alternatif_notu": "TAM OLARAK 180-220 kelimelik, ucretsiz/dusuk butceli secenekler hakkinda bir paragraf. Hangi araclarin ucretsiz katmani oldugunu, nelerden feragat edildigini anlat.",
  "hatalar": ["Sik yapilan hata 1 - TAM OLARAK 40-60 kelime aciklamali", "Hata 2 - 40-60 kelime", "Hata 3 - 40-60 kelime", "Hata 4 - 40-60 kelime", "Hata 5 - 40-60 kelime (4-5 hata arasi)"]
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
- 5 SORU BIRBIRINDEN TAMAMEN FARKLI olmali, hicbiri ayni seyi baska kelimelerle sormamali
  (orn. "hangi araclari kullanabilirim" ve "en iyi araclar hangileri" gibi benzer sorulari
  TEKRAR ETME, her soru farkli bir acidan yaklassin: fiyat, guvenlik, baslangic seviyesi,
  profesyonel kullanim, ozel bir senaryo gibi).

Su JSON formatinda cevap ver (baska hicbir sey yazma, tam olarak 5 soru-cevap):
{{
  "sss": [
    {{"soru": "Soru 1 (dogal, Google'da aranacak turden)", "cevap": "TAM OLARAK 80-110 kelimelik detayli cevap"}},
    {{"soru": "Soru 2", "cevap": "80-110 kelime"}},
    {{"soru": "Soru 3", "cevap": "80-110 kelime"}},
    {{"soru": "Soru 4", "cevap": "80-110 kelime"}},
    {{"soru": "Soru 5", "cevap": "80-110 kelime"}}
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
    html_parts.append(f"<p>{intro['giris']}</p>")
    html_parts.append("<h2>Neden Yapay Zeka Kullanmalısınız?</h2>")
    html_parts.append(f"<p>{intro['neden_ai']}</p>")

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


def run_one(guide_cfg: dict):
    from db import init_db, save_guide, get_comparison_by_slug, get_connection, normalize_name

    init_db()
    slug = guide_cfg["slug"]
    title = guide_cfg["title"]
    print(f"[{slug}] üretiliyor...")

    if guide_cfg["comparison_slug"]:
        comp = get_comparison_by_slug(guide_cfg["comparison_slug"])
        if not comp:
            print(f"  !! HATA: comparison '{guide_cfg['comparison_slug']}' bulunamadi, atlaniyor.")
            return
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


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
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

