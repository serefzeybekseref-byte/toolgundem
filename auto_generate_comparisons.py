"""
ASAMA 8: Kategoriler buyudukce otomatik karsilastirma (comparison) uretir.
Var olan gercek urun verisine dayanir (uydurma yok) - AI sadece
elindeki title_tr/summary_tr/why_use_it/key_features bilgisini
yapilandirilmis bir karsilastirmaya donusturur.
"""
import json
import os
import re
import time
from urllib.parse import urlparse
from dotenv import load_dotenv
load_dotenv()
from db import (
    init_db, get_connection, slugify, save_comparison, get_all_comparisons,
)
from generate_content import _generate_with_fallback
from quality_gate import check_comparison

init_db()

MIN_PRODUCTS = 5   # bu sayidan az urunu olan kategori icin karsilastirma uretilmez
MAX_ITEMS = 8       # bir karsilastirmada en fazla kac arac olsun
MAX_PER_BRAND = 2   # ayni sirketin (domain) en fazla kac urunu ayni listede olabilir

# Baslik karsilastirmasinda yok sayilacak, anlam tasimayan kelimeler (duplicate tespiti icin)
_STOPWORDS = {
    "en", "iyi", "ai", "yapay", "zeka", "araclari", "aracı", "araçları", "arac",
    "araç", "icin", "için", "5", "listesi", "karsilastirmasi", "karşılaştırması",
    "olarak", "ve", "ile", "destekli", "hazirlama", "hazırlama",
}


def _normalize_tokens(text: str) -> set:
    """Turkce karakterleri sadelestirip anlamli kelime kumesi cikarir (duplicate tespiti icin)."""
    text = text.lower()
    replacements = {"ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c"}
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    words = re.findall(r"[a-z0-9]+", text)
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def is_semantic_duplicate(candidate_title: str, existing_titles: list) -> str | None:
    """
    Slug ayni olmasa bile konu ortakligi varsa (ornek: 'Muzik Uretim Araclari' ile
    'Muzik Olusturma Araclari') True doner - ayni kategori iki farkli baslikla
    iki kez uretilmesin diye. En az 1 anlamli, ortak ve nadir (kisa stopword
    olmayan) kelime yeterli sayilir cunku CANDIDATE_TOPICS zaten dar/spesifik konular.
    """
    cand_tokens = _normalize_tokens(candidate_title)
    for existing in existing_titles:
        existing_tokens = _normalize_tokens(existing)
        overlap = cand_tokens & existing_tokens
        if overlap:
            return existing
    return None


def _brand_key(website: str, name: str) -> str:
    """Urunun 'marka'sini domain'den cikarir (ornek: chat.openai.com -> openai)."""
    try:
        netloc = urlparse(website).netloc.lower()
        parts = netloc.replace("www.", "").split(".")
        if len(parts) >= 2:
            return parts[-2]
    except Exception:
        pass
    return name.lower().split()[0] if name else "?"

# topic etiketi -> (baslik, slug, min_urun_ustyazi)
CANDIDATE_TOPICS = {
    "SEO": "En Iyi AI SEO Araclari",
    "Otomasyon": "En Iyi AI Otomasyon ve Ajan Araclari",
    "Uretkenlik": "En Iyi AI Uretkenlik Araclari",
    "NoCode": "En Iyi No-Code AI Uygulama Gelistirme Araclari",
    "Ses": "En Iyi AI Ses ve Seslendirme Araclari",
    "Muzik": "En Iyi AI Muzik Uretim Araclari",
    "WebSitesi": "En Iyi AI Web Sitesi Olusturucular",
    "Avatar": "En Iyi AI Avatar ve Dijital Insan Araclari",
    "Transkripsiyon": "En Iyi AI Transkripsiyon Araclari",
    "Satis": "En Iyi AI Satis ve CRM Araclari",
    "Tasarim": "En Iyi AI Tasarim Araclari",
    "Eticaret": "En Iyi AI E-Ticaret Araclari",
    "Ceviri": "En Iyi AI Ceviri Araclari",
    "MusteriDestegi": "En Iyi AI Musteri Destek Araclari",
    "Arastirma": "En Iyi AI Arastirma ve Veri Analizi Araclari",
}

def get_top_products_for_topic(topic: str, limit: int = MAX_ITEMS):
    """
    Oy sayisina gore siralar ama ayni markadan (domain) en fazla MAX_PER_BRAND
    urun alir - yoksa ornegin OpenAI'nin ChatGPT/GPT-4o/Operator/Codex gibi
    urunleri tek basina listenin cogunu kaplayabilir.
    """
    conn = get_connection()
    pattern = f"%{topic}%"
    rows = conn.execute("""
        SELECT * FROM products WHERE topics LIKE ?
        ORDER BY votes DESC
    """, (pattern,)).fetchall()
    conn.close()
    all_products = [dict(r) for r in rows]

    brand_counts = {}
    selected = []
    for p in all_products:
        brand = _brand_key(p.get("website", ""), p.get("original_name", ""))
        if brand_counts.get(brand, 0) >= MAX_PER_BRAND:
            continue
        selected.append(p)
        brand_counts[brand] = brand_counts.get(brand, 0) + 1
        if len(selected) >= limit:
            break
    return selected


def existing_comparison_slugs():
    return {c["slug"] for c in get_all_comparisons()}


def build_comparison_via_ai(topic_label: str, products: list) -> dict:
    """Verilen gercek urun verisinden yapilandirilmis karsilastirma ureten AI cagrisi."""
    product_text = ""
    for p in products:
        product_text += (
            f"- İsim: {p.get('original_name')}\n"
            f"  Özet: {p.get('summary_tr', '')}\n"
            f"  Neden kullanılır: {p.get('why_use_it', '')}\n"
            f"  Özellikler: {p.get('key_features', '')}\n"
            f"  Fiyatlandırma: {p.get('pricing_type', '') or 'Bilinmiyor'}\n"
            f"  Website: {p.get('website', '')}\n\n"
        )

    prompt = f"""Sen ToolGündem için çalışan kıdemli bir teknoloji editörüsün.
Aşağıda "{topic_label}" kategorisine giren, veritabanımızda zaten kayıtlı gerçek araçların bilgileri var.
Bu bilgilere DAYANARAK bir karşılaştırma tablosu oluştur. YENİ BİLGİ UYDURMA, sadece verilenden çıkarım yap.

Araçlar:
{product_text}

Kurallar:
- SADECE Türkçe yaz.
- Her araç için 1-10 arası bir puan (score) ver (verilen bilgilerin kalitesine/kapsamına göre mantıklı bir sıralama yap).
- pricing: verilen fiyatlandırma tipini kısa Türkçe ifadeye çevir (ör. "Freemium", "Ücretsiz", "Ücretli").
- best_for: kime uygun olduğunu tek cümlede özetle.
- pros: 2-3 maddelik güçlü yön listesi.
- cons: 1-2 maddelik zayıf yön listesi (verilenden çıkarım yapamıyorsan genel/makul bir sınırlama yaz, ör. "Ücretsiz planda kısıtlı kullanım").
- intro: kategori için 2-3 cümlelik giriş metni üret.
- title: "{topic_label}" ifadesini temel alan SEO'ya uygun bir başlık üret (60 karakteri geçmesin).
- title ve intro içine KESİNLİKLE spesifik bir yıl (2024, 2025 gibi) YAZMA - bu içerik zamanla
  bayatlar ve yanlış görünür, "en güncel" gibi zamana bağlı olmayan ifadeler kullan.

Yalnızca şu JSON formatında cevap ver:
{{"title": "...", "intro": "...", "items": [
  {{"name": "...", "score": 9.2, "pricing": "...", "best_for": "...", "pros": ["...", "..."], "cons": ["..."], "website": "..."}}
]}}
"""
    groq_extra = {"temperature": 0.4, "response_format": {"type": "json_object"}}
    return _generate_with_fallback(prompt, groq_extra)

def run():
    existing = existing_comparison_slugs()
    existing_titles = [c["title"] for c in get_all_comparisons()]
    created, skipped, rejected = 0, 0, 0
    rejection_report = []

    for topic, title_hint in CANDIDATE_TOPICS.items():
        slug = slugify(title_hint)
        if slug in existing:
            skipped += 1
            continue

        dup = is_semantic_duplicate(title_hint, existing_titles)
        if dup:
            print(f"[atlandi] {topic}: '{title_hint}' zaten var olan '{dup}' ile konu ortakligi tasiyor (semantik duplicate)")
            skipped += 1
            continue

        products = get_top_products_for_topic(topic, MAX_ITEMS)
        if len(products) < MIN_PRODUCTS:
            print(f"[atlandi] {topic}: sadece {len(products)} urun var (min {MIN_PRODUCTS})")
            continue

        print(f"[uretiliyor] {topic} -> {len(products)} urunle karsilastirma...")
        try:
            ai_data = build_comparison_via_ai(title_hint, products)
            items = []
            for i, it in enumerate(ai_data.get("items", []), start=1):
                items.append({
                    "rank": i,
                    "name": it.get("name", ""),
                    "score": float(it.get("score", 7.0)),
                    "pricing": it.get("pricing", ""),
                    "best_for": it.get("best_for", ""),
                    "pros": it.get("pros", []),
                    "cons": it.get("cons", []),
                    "website": it.get("website", ""),
                })
            if not items:
                print(f"  !! bos sonuc, atlandi")
                continue

            title = ai_data.get("title", title_hint)
            intro = ai_data.get("intro", "")
            by_name = {p["original_name"].lower(): p for p in products}
            ok, problems = check_comparison(title, intro, items, source_products_by_name=by_name)
            if not ok:
                print(f"  !! KALITE KAPISI REDDETTI ({len(problems)} sorun):")
                for pr in problems:
                    print(f"     - {pr}")
                rejected += 1
                rejection_report.append({"topic": topic, "title": title, "problems": problems})
                continue

            save_comparison(slug, title, intro, items)
            print(f"  -> kaydedildi: /karsilastirma/{slug}")
            created += 1
        except Exception as e:
            print(f"  !! HATA: {e}")
        time.sleep(2.5)

    print(f"\nBitti. Olusturulan: {created}, Atlanan (zaten var/az urun): {skipped}, Kalite kapisinda reddedilen: {rejected}")

    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a", encoding="utf-8") as f:
            f.write(f"rejected_count={rejected}\n")
            if rejection_report:
                report_lines = []
                for r in rejection_report:
                    report_lines.append(f"### {r['title']} ({r['topic']})")
                    for pr in r["problems"]:
                        report_lines.append(f"- {pr}")
                f.write("rejection_report<<EOF\n")
                f.write("\n".join(report_lines) + "\n")
                f.write("EOF\n")


if __name__ == "__main__":
    run()
