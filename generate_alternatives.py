"""
"X Alternatifleri" rehber sayfalari uretir. Var olan guides altyapisini kullanir
(ayni tablo, ayni /rehber/<slug> route'u, ayni sablon) - yeni route/template gerekmez.

Sadece GERCEKTEN taninir/aranir markalar icin uretilir (Product Hunt'taki niş
araclar icin degil) - cunku arama hacmi olmayan bir "alternatifleri" sayfasi
hem zaman hem kalite kapisi acisindan israf olur.

Veri kaynagi: comparison_items tablosu - bu markalarin gercek pricing/best_for/
pros/cons bilgisi zaten var, LLM'e bu gercek veriyi baglam olarak veriyoruz
(uydurma bilgi riskini azaltmak icin).
"""
import sys
import re
import json
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

from db import get_connection, init_db, save_guide
from generate_content import _generate_with_fallback

# Sadece genis taninirligi olan, gercek arama hacmi beklenen markalar.
TARGET_BRANDS = [
    "ChatGPT", "Notion AI", "Canva AI (Magic Design)", "Grammarly",
    "Midjourney V7", "GitHub Copilot", "Gamma", "ElevenLabs",
]

_SUSPICIOUS_WORDS = [
    "thus", "however", "the", "and", "with", "your", "this", "that",
    "will", "now", "successfully", "successful", "were", "its", "onto",
    "erfolgreich", "und", "mit", "für", "das", "die", "der", "ist", "nicht", "auch",
    "mejores", "que", "con", "los", "las", "una", "esta",
    "avec", "pour", "dans",
]
_suspicious_pattern = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in _SUSPICIOUS_WORDS) + r")\b",
    flags=re.IGNORECASE,
)


def _slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "-", s.strip())
    s = s.replace("ı", "i").replace("ğ", "g").replace("ü", "u").replace("ş", "s").replace("ö", "o").replace("ç", "c")
    return s


def get_brand_context(brand_name: str, limit=8):
    """Bu marka hangi karsilastirmalarda geciyor, gercek verisi (pricing/best_for/pros/cons) ne."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT ci.name, ci.pricing, ci.best_for, ci.pros, ci.cons, c.title as comparison_title
        FROM comparison_items ci
        JOIN comparisons c ON c.id = ci.comparison_id
        WHERE ci.name = ?
        LIMIT ?
    """, (brand_name, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_real_alternatives(brand_name: str, exclude_name: str, limit=6):
    """Ayni karsilastirma sayfalarinda gecen DIGER (gercek, veritabanindaki) araclari bulur -
    boylece LLM'e uydurma alternatif isim uretme ihtimalini en aza indiriyoruz."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT DISTINCT ci2.name, ci2.pricing, ci2.best_for, ci2.rank
        FROM comparison_items ci1
        JOIN comparison_items ci2 ON ci2.comparison_id = ci1.comparison_id AND ci2.name != ci1.name
        WHERE ci1.name = ?
        ORDER BY ci2.rank ASC
        LIMIT ?
    """, (exclude_name, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def build_intro_prompt(brand: str, context: list) -> str:
    ctx_text = "\n".join([
        f"- {c['comparison_title']}: fiyat={c.get('pricing','?')}, en iyi oldugu alan={c.get('best_for','?')}"
        for c in context
    ]) or "Ozel veri yok."
    return f"""Sen deneyimli bir Turkce teknoloji editorusun. "{brand} Alternatifleri" konulu bir SEO
rehberinin GIRIS bolumlerini yaziyorsun.

{brand} HAKKINDA GERCEK VERI (bunun disina cikma, uydurma bilgi verme):
{ctx_text}
{_COMMON_RULES}

Su JSON formatinda cevap ver (baska hicbir sey yazma):
{{
  "title": "{brand} Alternatifleri: 2026 icin En Iyi Secenekler",
  "meta_description": "150-160 karakterlik SEO ozeti",
  "excerpt": "1-2 cumlelik giris ozeti",
  "hizli_ozet": "TAM OLARAK 2-3 cumlelik dogrudan cevap: hangi alternatif hangi durumda one cikiyor. 'Kisa cevap:' ile BASLAMA, bu otomatik ekleniyor.",
  "giris": "TAM OLARAK 180-220 kelimelik giris paragrafi: {brand} kullanicilari neden alternatif arar (fiyat, ozellik eksikligi, dil destegi vb - GERCEK VERIYE dayanarak, uydurma sebep uretme)."
}}
"""


def build_alternatives_body_prompt(brand: str, alternatives: list) -> str:
    alt_text = "\n".join([
        f"- {a['name']} (fiyat: {a.get('pricing','?')}, en iyi oldugu alan: {a.get('best_for','?')})"
        for a in alternatives
    ])
    return f"""Sen deneyimli bir Turkce teknoloji editorusun. "{brand} Alternatifleri" rehberinin ANA
GOVDESINI yaziyorsun.

SADECE su GERCEK alternatif araclari ele al, BASKA/UYDURMA ARAC ISMI EKLEME:
{alt_text}
{_COMMON_RULES}

Su JSON formatinda cevap ver (baska hicbir sey yazma):
{{
  "alternatifler": [
    {{"isim": "arac adi (yukaridaki listeden BIREBIR)", "aciklama": "TAM OLARAK 70-100 kelime: ne ise yarar, {brand}'tan farki, kimler icin uygun"}},
    ... (listedeki HER arac icin bir tane, hepsi icin)
  ]
}}
"""


def build_outro_prompt(brand: str, alternatives: list) -> str:
    names = ", ".join(a["name"] for a in alternatives)
    return f"""Sen deneyimli bir Turkce teknoloji editorusun. "{brand} Alternatifleri" rehberinin SONUC
ve SSS bolumlerini yaziyorsun. Ele alinan alternatifler: {names}.
{_COMMON_RULES}

Su JSON formatinda cevap ver (baska hicbir sey yazma):
{{
  "sonuc": "TAM OLARAK 100-150 kelimelik kisa sonuc paragrafi, hangi durumda hangi aracin secilmesi gerektigini ozetler",
  "sss": [
    {{"soru": "...", "cevap": "TAM OLARAK 100-140 kelime"}},
    {{"soru": "...", "cevap": "TAM OLARAK 100-140 kelime"}},
    {{"soru": "...", "cevap": "TAM OLARAK 100-140 kelime"}}
  ]
}}
"""


_COMMON_RULES = """
KURALLAR:
- SADECE Turkce yaz. Ingilizce/Almanca/Ispanyolca/Fransizca TEK BIR KELIME bile sizmasin.
- "ideal bir secenektir" gibi klise ifadeleri TEKRARLAMA, her cumle farkli olsun.
- Ton: tarafsiz, bilgilendirici, iddiali degil.
"""


def _has_language_leak(text: str) -> bool:
    return bool(_suspicious_pattern.search(text))


def _md_h3_to_html(text: str) -> str:
    lines = text.split("\n")
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("## "):
            out.append(f"<h3>{line[3:].strip()}</h3>")
        else:
            out.append(f"<p>{line}</p>")
    return "\n".join(out)


def _call_section(prompt: str, max_tokens=1500):
    attempts = 0
    while attempts < 3:
        raw = _generate_with_fallback(
            prompt,
            groq_payload_extra={"temperature": 0.6, "response_format": {"type": "json_object"}},
            max_tokens=max_tokens,
        )
        if not _has_language_leak(json.dumps(raw, ensure_ascii=False)):
            return raw
        attempts += 1
        print(f"    (dil sizintisi, deneme {attempts+1}/3)")
    return None


def generate_one(brand: str, dry_run=False):
    print(f"\n[{brand}] Alternatifleri uretiliyor...")
    context = get_brand_context(brand)
    alternatives = get_real_alternatives(brand, brand)
    if len(alternatives) < 3:
        print(f"  ATLANDI: yeterli gercek alternatif verisi yok ({len(alternatives)} adet)")
        return None

    print("  (bolum 1/3: giris + hizli ozet)")
    intro = _call_section(build_intro_prompt(brand, context))
    print("  (bolum 2/3: alternatifler)")
    body = _call_section(build_alternatives_body_prompt(brand, alternatives), max_tokens=2000)
    print("  (bolum 3/3: sonuc + SSS)")
    outro = _call_section(build_outro_prompt(brand, alternatives))

    if not intro or not body or not outro:
        print(f"  HATA: bir bolum 3 denemede de temiz uretilemedi, atlaniyor.")
        return None

    # Kalite kapisi: minimum kelime sayisi kontrolu
    body_text = " ".join([
        intro.get("giris", ""),
        " ".join(a.get("aciklama", "") for a in body.get("alternatifler", [])),
        outro.get("sonuc", ""),
        " ".join(f["cevap"] for f in outro.get("sss", [])),
    ])
    word_count = len(body_text.split())
    if word_count < 350:
        print(f"  ATLANDI: kelime sayisi cok dusuk ({word_count})")
        return None

    # HTML birlestir - slug eslestirip ic link ekliyoruz (SEO + kullanici deneyimi)
    from db import normalize_name
    conn = get_connection()
    slug_map = {}
    for a in body.get("alternatifler", []) + [{"isim": brand}]:
        name = a.get("isim") or a.get("name")
        row = conn.execute(
            "SELECT slug FROM products WHERE normalized_name = ?", (normalize_name(name),)
        ).fetchone()
        if row:
            slug_map[name] = dict(row)["slug"]
    conn.close()
    related_tool_slugs = list(slug_map.values())

    html_parts = []
    if intro.get("hizli_ozet"):
        html_parts.append(f"<div class='guide-quick-answer'><strong>⚡ Kısa cevap:</strong> {intro['hizli_ozet']}</div>")
    html_parts.append(f"<p>{intro['giris']}</p>")
    html_parts.append(f"<h2>{brand} Alternatifleri</h2>")
    for a in body.get("alternatifler", []):
        name = a["isim"]
        if name in slug_map:
            html_parts.append(f"<h3><a href='/urun/{slug_map[name]}'>{name}</a></h3><p>{a['aciklama']}</p>")
        else:
            html_parts.append(f"<h3>{name}</h3><p>{a['aciklama']}</p>")
    html_parts.append(f"<h2>Sonuç</h2><p>{outro['sonuc']}</p>")
    if outro.get("sss"):
        html_parts.append("<h2>Sık Sorulan Sorular</h2>")
        for f in outro["sss"]:
            html_parts.append(f"<h3>{f['soru']}</h3><p>{f['cevap']}</p>")
    content_html = "\n".join(html_parts)

    slug = _slugify(brand) + "-alternatifleri"
    title = intro["title"].replace("{{Yil}}", "2026")

    print(f"  -> kelime sayisi: {word_count}")

    if dry_run:
        print(f"  [DRY RUN] kaydedilmedi: /rehber/{slug}")
        return {"slug": slug, "title": title, "word_count": word_count}

    save_guide(
        slug=slug,
        title=title,
        meta_description=intro["meta_description"],
        excerpt=intro["excerpt"],
        content_html=content_html,
        related_topic="",
        related_tool_slugs=related_tool_slugs,
        related_comparison_slugs=[],
    )
    print(f"  -> kaydedildi: /rehber/{slug}")
    return {"slug": slug, "title": title, "word_count": word_count}


def run_all(dry_run=False):
    init_db()
    results = []
    for brand in TARGET_BRANDS:
        try:
            r = generate_one(brand, dry_run=dry_run)
            if r:
                results.append(r)
        except Exception as e:
            print(f"  HATA ({brand}): {e}")
    print(f"\nToplam {len(results)}/{len(TARGET_BRANDS)} alternatif sayfasi uretildi.")
    return results


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    only = None
    for arg in sys.argv[1:]:
        if arg in TARGET_BRANDS:
            only = arg
    if only:
        init_db()
        generate_one(only, dry_run=dry)
    else:
        run_all(dry_run=dry)
