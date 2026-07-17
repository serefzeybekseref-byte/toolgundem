"""
ASAMA 8: Kategoriler buyudukce otomatik karsilastirma (comparison) uretir.
Var olan gercek urun verisine dayanir (uydurma yok) - AI sadece
elindeki title_tr/summary_tr/why_use_it/key_features bilgisini
yapilandirilmis bir karsilastirmaya donusturur.
"""
import json
import time
from db import (
    init_db, get_connection, slugify, save_comparison, get_all_comparisons,
)
from generate_content import _generate_with_fallback

init_db()

MIN_PRODUCTS = 5   # bu sayidan az urunu olan kategori icin karsilastirma uretilmez
MAX_ITEMS = 8       # bir karsilastirmada en fazla kac arac olsun

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
    conn = get_connection()
    pattern = f"%{topic}%"
    rows = conn.execute("""
        SELECT * FROM products WHERE topics LIKE ?
        ORDER BY votes DESC LIMIT ?
    """, (pattern, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


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

Yalnızca şu JSON formatında cevap ver:
{{"title": "...", "intro": "...", "items": [
  {{"name": "...", "score": 9.2, "pricing": "...", "best_for": "...", "pros": ["...", "..."], "cons": ["..."], "website": "..."}}
]}}
"""
    groq_extra = {"temperature": 0.4, "response_format": {"type": "json_object"}}
    return _generate_with_fallback(prompt, groq_extra)

def run():
    existing = existing_comparison_slugs()
    created, skipped = 0, 0

    for topic, title_hint in CANDIDATE_TOPICS.items():
        slug = slugify(title_hint)
        if slug in existing:
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
            save_comparison(slug, ai_data.get("title", title_hint), ai_data.get("intro", ""), items)
            print(f"  -> kaydedildi: /karsilastirma/{slug}")
            created += 1
        except Exception as e:
            print(f"  !! HATA: {e}")
        time.sleep(2.5)

    print(f"\nBitti. Olusturulan: {created}, Atlanan (zaten var/az urun): {skipped}")


if __name__ == "__main__":
    run()
