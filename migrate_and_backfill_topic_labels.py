"""
Topic Label Migration + Backfill
1) TOPIC_LABELS (app.py'deki statik sozluk) icerigini DB'deki yeni
   'topic_labels' tablosuna tasir.
2) DB'de gecen ama hicbir yerde cevirisi olmayan (256 adet) ham kategoriyi
   Groq/Gemini/NIM fallback zinciriyle toplu Turkce'ye cevirip ayni tabloya yazar.

Bundan sonra app.py, TOPIC_LABELS + DB'deki topic_labels tablosunu birlikte
kullanacak (bkz. db.get_topic_labels_map). Boylece yeni PH kategorileri
koda dokunmadan, pipeline icinde otomatik cevrilip DB'ye eklenebilir hale gelir
(bkz. auto_translate_new_topics fonksiyonu, gelecekteki pipeline entegrasyonu icin).

Kullanim:
    python migrate_and_backfill_topic_labels.py
"""
import json
from dotenv import load_dotenv
load_dotenv()

import db
from generate_content import _generate_with_fallback
import app as flask_app

BATCH_SIZE = 40  # tek LLM cagrisinda cevrilecek kategori sayisi


def ensure_table():
    conn = db.get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS topic_labels (
            raw_topic TEXT PRIMARY KEY,
            label_tr TEXT NOT NULL,
            source TEXT DEFAULT 'manual'
        )
    """)
    conn.commit()
    conn.close()


def migrate_existing_dict():
    """app.py'deki TOPIC_LABELS sozlugunu DB'ye tasir (source='manual')."""
    conn = db.get_connection()
    count = 0
    for raw, label in flask_app.TOPIC_LABELS.items():
        existing = conn.execute("SELECT 1 FROM topic_labels WHERE raw_topic = ?", (raw,)).fetchone()
        if existing:
            continue
        conn.execute(
            "INSERT INTO topic_labels (raw_topic, label_tr, source) VALUES (?, ?, 'manual')",
            (raw, label)
        )
        count += 1
    conn.commit()
    conn.close()
    print(f"Mevcut sozlukten tasinan: {count}")


def get_missing_topics():
    conn = db.get_connection()
    rows = conn.execute("SELECT topics FROM products WHERE topics IS NOT NULL AND topics != ''").fetchall()
    known = conn.execute("SELECT raw_topic FROM topic_labels").fetchall()
    conn.close()

    known_set = {dict(r)["raw_topic"] for r in known}
    all_topics = set()
    for r in rows:
        for t in dict(r)["topics"].split(","):
            t = t.strip()
            if t:
                all_topics.add(t)
    return sorted(all_topics - known_set)


def translate_batch(topics):
    """LLM'e bir liste kategori adi verir, JSON {raw: turkce_etiket} alir."""
    prompt = f"""Aşağıda Product Hunt'tan gelen İngilizce/karışık kategori adları var.
Her birini KISA (1-3 kelime), doğal, site kategori etiketi olarak kullanılabilecek
Türkçe karşılığına çevir. Marka/ürün adları (örn: Shopify, WordPress, AWS, LinkedIn,
Notion, Twitter, YouTube) OLDUĞU GİBİ bırakılmalı, çevrilmemeli. Kısaltmalar
(API, SDK, CRM, SEO, UI, iOS gibi) da olduğu gibi kalabilir.

ÇOK ÖNEMLİ: Çevirilerinde Türkçe'ye özgü harfleri (ı, ğ, ü, ş, ö, ç) MUTLAKA doğru
kullan. Örnek: "Tasarım Araçları" yaz, "Tasarim Araclari" YAZMA. "İş Zekası" yaz,
"Is Zekasi" YAZMA. Türkçe karakterleri ASCII harflere (i, g, u, s, o, c) indirgeme.

Kategoriler:
{json.dumps(topics, ensure_ascii=False)}

SADECE geçerli JSON döndür, başka hiçbir metin ekleme. Format:
{{"orijinal_kategori_adi": "Türkçe Etiket", ...}}
Her orijinal kategori tam olarak yukarıdaki listedeki gibi (büyük/küçük harf dahil) key olmalı."""

    groq_extra = {"temperature": 0.2, "response_format": {"type": "json_object"}}
    result = _generate_with_fallback(prompt, groq_extra)
    return result


def run():
    ensure_table()
    migrate_existing_dict()

    missing = get_missing_topics()
    print(f"Cevrilecek kategori sayisi: {len(missing)}")

    conn = db.get_connection()
    total_translated = 0
    for i in range(0, len(missing), BATCH_SIZE):
        batch = missing[i:i + BATCH_SIZE]
        print(f"\nParti {i // BATCH_SIZE + 1}: {len(batch)} kategori cevriliyor...")
        try:
            translations = translate_batch(batch)
        except Exception as e:
            print(f"  HATA: {e}")
            continue

        if not isinstance(translations, dict):
            print(f"  UYARI: beklenmeyen format, atlaniyor: {type(translations)}")
            continue

        for raw in batch:
            label = translations.get(raw)
            if not label:
                # LLM bu terimi atlamis olabilir (buyuk/kucuk harf farki vb.) - ham haliyle birak
                label = raw
                source = "fallback"
            else:
                source = "ai"
            conn.execute(
                "INSERT INTO topic_labels (raw_topic, label_tr, source) VALUES (?, ?, ?) "
                "ON CONFLICT (raw_topic) DO UPDATE SET label_tr = EXCLUDED.label_tr, source = EXCLUDED.source"
                if db.USE_POSTGRES else
                "INSERT OR REPLACE INTO topic_labels (raw_topic, label_tr, source) VALUES (?, ?, ?)",
                (raw, label, source)
            )
            total_translated += 1
        conn.commit()

    conn.close()
    print(f"\nTOPLAM: {total_translated} kategori isaretlendi/cevrildi.")


if __name__ == "__main__":
    run()
