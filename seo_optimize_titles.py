# -*- coding: utf-8 -*-
"""
Karsilastirma basliklarini arama niyetine (search intent) gore optimize eder:
- Sabit "5 Arac" ifadesi kaldirilir (gercek arac sayisi degisken, yaniltici olabilir)
- Tutarli "En Iyi AI X Araclari" kalibi kullanilir (kullanicilarin gercekte
  Google'a yazdigi ifadeye yakin)
- Yil, zaten template'te H1 ve <title> etiketinde dinamik olarak ekleniyor,
  DB'de sabit yazilmiyor (gelecek yil "eskimis" gorunmesin diye).
"""
from dotenv import load_dotenv
load_dotenv()
from db import get_connection

TITLE_UPDATES = {
    "ai-logo-tasarim-araclari": "En İyi AI Logo Tasarım Araçları",
    "ai-pdf-araclari": "En İyi AI PDF Okuma ve Özetleme Araçları",
    "en-iyi-ai-seo-araclari": "En İyi AI SEO Araçları",
    "en-iyi-ai-otomasyon-ve-ajan-araclari": "En İyi AI Otomasyon ve Ajan Araçları",
    "en-iyi-no-code-ai-uygulama-gelistirme-araclari": "En İyi No-Code AI Uygulama Geliştirme Araçları",
    "ai-sunum-araclari": "En İyi AI Sunum (Slayt) Araçları",
    "ai-yazi-araclari": "En İyi AI Yazı ve İçerik Üretim Araçları",
    "ai-sohbet-botlari": "En İyi AI Sohbet Botları ve Asistanları",
    "ai-kod-asistanlari": "En İyi AI Kod Asistanları",
    "video-ureten-ai-araclari": "En İyi Metinden Video Üreten AI Araçları",
    "metinden-goruntu-olusturan-ai-araclari": "En İyi Metinden Görüntü Oluşturan AI Araçları",
    "toplanti-notu-transkripsiyon-araclari": "En İyi AI Toplantı Notu ve Transkripsiyon Araçları",
    "ai-ozgecmis-hazirlama-araclari": "En İyi AI Özgeçmiş (CV) Hazırlama Araçları",
    "ai-muzik-uretme-araclari": "En İyi AI Müzik Üretme Araçları",
    "en-iyi-ai-ses-ve-seslendirme-araclari": "En İyi AI Ses ve Seslendirme Araçları",
    "en-iyi-ai-web-sitesi-olusturucular": "En İyi AI Web Sitesi Oluşturucular",
    "en-iyi-ai-avatar-ve-dijital-insan-araclari": "En İyi AI Avatar ve Dijital İnsan Araçları",
    "en-iyi-ai-uretkenlik-araclari": "En İyi AI Üretkenlik Araçları",
    "en-iyi-ai-satis-ve-crm-araclari": "En İyi AI Satış ve CRM Araçları",
    "en-iyi-ai-tasarim-araclari": "En İyi AI Tasarım Araçları",
}


def run():
    conn = get_connection()
    updated = 0
    for slug, new_title in TITLE_UPDATES.items():
        result = conn.execute("UPDATE comparisons SET title = ? WHERE slug = ?", (new_title, slug))
        updated += 1
        print(f"guncellendi: {slug} -> {new_title}")
    conn.commit()
    conn.close()
    print(f"\nToplam {updated} baslik guncellendi.")


if __name__ == "__main__":
    run()
