# -*- coding: utf-8 -*-
from dotenv import load_dotenv
load_dotenv()
from db import init_db, save_comparison

init_db()

items = [
    {
        "rank": 1, "name": "Fathom", "score": 9.2,
        "pricing": "Ucretsiz (sinirsiz kayit) + Team plani 19$/kullanici/ay",
        "best_for": "Bireysel kullanicilar ve kucuk ekipler, butce dostu",
        "pros": ["Ucretsiz plan sinirsiz kayit sunuyor", "Zoom/Meet/Teams entegrasyonu", "Kurulumu kolay"],
        "cons": ["Ileri seviye CRM entegrasyonlari ucretli planda"],
        "website": "https://fathom.video",
    },
    {
        "rank": 2, "name": "Fellow", "score": 9.0,
        "pricing": "Ucretsiz sinirli + Team plani ~75$/ay (5 kullanici)",
        "best_for": "Guvenlik odakli kurumsal ekipler (SOC 2, GDPR, HIPAA)",
        "pros": ["Toplanti oncesi/sonrasi tam dongu yonetimi", "92 dil destegi", "50+ kurumsal arac entegrasyonu"],
        "cons": ["Kucuk ekipler icin fiyat/ozellik dengesi agir olabilir"],
        "website": "https://fellow.app",
    },
    {
        "rank": 3, "name": "Fireflies.ai", "score": 8.7,
        "pricing": "Ucretsiz sinirli + Pro 18$/ay + Business 29$/ay",
        "best_for": "Satis ekipleri, CRM entegrasyonu onemli olanlar",
        "pros": ["Guclu Salesforce/HubSpot entegrasyonu", "Duygu analizi ve konu takibi", "60+ dil destegi"],
        "cons": ["Toplantiya bot katilimi bazi katilimcilari rahatsiz edebilir"],
        "website": "https://fireflies.ai",
    },
    {
        "rank": 4, "name": "Otter.ai", "score": 8.3,
        "pricing": "Ucretsiz sinirli + 16.99$/ay",
        "best_for": "Gercek zamanli transkripsiyon, bilinen/yerlesik marka",
        "pros": ["Canli transkripsiyon ekranda anlik gorunur", "Kullanimi basit arayuz"],
        "cons": ["Sadece Ingilizce/Ispanyolca/Fransizca destegi", "Ingilizce disi dillerde dogruluk degisken"],
        "website": "https://otter.ai",
    },
    {
        "rank": 5, "name": "Granola", "score": 8.0,
        "pricing": "Ucretsiz (30 gun gecmis siniri) + 14$/ay",
        "best_for": "Sade, dagitici olmayan not deneyimi isteyenler",
        "pros": ["Butceye uygun giris fiyati", "Sade ve odakli arayuz"],
        "cons": ["Ucretsiz planda 30 gunden eski notlara erisim yok"],
        "website": "https://granola.ai",
    },
]

save_comparison(
    slug="toplanti-notu-transkripsiyon-araclari",
    title="Toplanti Notu ve Transkripsiyon Icin En Iyi 5 AI Araci",
    intro="2026 itibariyla en cok tercih edilen AI toplanti notu ve transkripsiyon araclarini "
          "fiyat, dogruluk ve entegrasyon acisindan karsilastirdik.",
    items=items,
)

print("Karsilastirma eklendi: /karsilastirma/toplanti-notu-transkripsiyon-araclari")
