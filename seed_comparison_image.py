# -*- coding: utf-8 -*-
from db import init_db, save_comparison

init_db()

items = [
    {
        "rank": 1, "name": "Midjourney V7", "score": 9.4,
        "pricing": "10 - 120 $/ay (ucretsiz deneme yok)",
        "best_for": "Sanatsal / estetik gorseller",
        "pros": ["En yuksek sanatsal kalite", "Guclu stil tutarliligi", "Web arayuzu artik mevcut"],
        "cons": ["Ucretsiz plan yok", "Metin yazma konusunda zayif", "Prompt ogrenme egrisi var"],
        "website": "https://www.midjourney.com",
    },
    {
        "rank": 2, "name": "ChatGPT (GPT Image 2)", "score": 9.3,
        "pricing": "Ucretsiz sinirli + ChatGPT Plus 20$/ay",
        "best_for": "Gercekcilik, prompt takibi, kolay kullanim",
        "pros": ["Sohbet ederek duzenleme", "Yuksek gercekcilik", "Kolay kullanim"],
        "cons": ["Yogun saatlerde yavaslayabilir", "Ticari lisans sartlari karisik"],
        "website": "https://chatgpt.com",
    },
    {
        "rank": 3, "name": "FLUX.2 Pro", "score": 9.0,
        "pricing": "Kullanim basina ~0.08$/gorsel (API)",
        "best_for": "Gelistiriciler, urun gorselleri, kontrol",
        "pros": ["Acik agirlikli secenek mevcut", "Ticari kullanima uygun (Apache 2.0)", "Yuksek gercekcilik"],
        "cons": ["API/teknik bilgi gerektirir", "Hazir arayuz sinirli"],
        "website": "https://blackforestlabs.ai",
    },
    {
        "rank": 4, "name": "Ideogram 3.0", "score": 8.8,
        "pricing": "Ucretsiz (gunluk 10 gorsel) + ucretli planlar",
        "best_for": "Gorsel icinde okunabilir metin/yazi",
        "pros": ["Metin yazma dogrulugu %90+", "Comert ucretsiz plan", "Logo/poster islerinde guclu"],
        "cons": ["Sanatsal cesitlilik Midjourney kadar genis degil"],
        "website": "https://ideogram.ai",
    },
    {
        "rank": 5, "name": "Adobe Firefly", "score": 8.5,
        "pricing": "Ucretsiz sinirli + Creative Cloud paketleri",
        "best_for": "Ticari/kurumsal guvenli kullanim",
        "pros": ["Telif hakki tazminati garantisi", "Photoshop/Illustrator entegrasyonu", "Lisansli veriyle egitildi"],
        "cons": ["Zirve kalite diger modellerin gerisinde kalabiliyor"],
        "website": "https://firefly.adobe.com",
    },
]

save_comparison(
    slug="metinden-goruntu-olusturan-ai-araclari",
    title="Metinden Goruntu Olusturan En Iyi 5 AI Araci",
    intro="2026 itibariyla aktif kullanilabilen, en cok tercih edilen metinden-gorsele AI araclarini "
          "kalite, fiyat ve kullanim kolayligina gore karsilastirdik.",
    items=items,
)

print("Karsilastirma eklendi: /karsilastirma/metinden-goruntu-olusturan-ai-araclari")
