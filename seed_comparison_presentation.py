# -*- coding: utf-8 -*-
from dotenv import load_dotenv
load_dotenv()
from db import init_db, save_comparison

init_db()

items = [
    {
        "rank": 1, "name": "Gamma", "score": 9.0,
        "pricing": "Ucretsiz sinirli + Plus/Pro 8-20 $/ay",
        "best_for": "Metinden hizli, tasarim odakli sunum/dokuman uretimi",
        "pros": ["En hizli metin-to-slayt donusumu", "Modern, sablon disi tasarimlar", "Web sayfasi/dokuman modu da var"],
        "cons": ["Karmasik veri/grafik entegrasyonu sinirli"],
        "website": "https://gamma.app",
    },
    {
        "rank": 2, "name": "Beautiful.ai", "score": 8.6,
        "pricing": "Pro 12-40 $/ay",
        "best_for": "Kurumsal, marka kurallarina uygun sunumlar",
        "pros": ["Akilli slayt sablonlari otomatik hizalanir", "Marka kiti/takim ozellikleri"],
        "cons": ["Ucretsiz plan yok", "Yaratici ozgurluk Gamma'ya gore daha kisitli"],
        "website": "https://www.beautiful.ai",
    },
    {
        "rank": 3, "name": "Tome", "score": 8.3,
        "pricing": "Ucretsiz sinirli + ucretli planlar",
        "best_for": "Anlatı tabanli, AI ile birlikte yaratici sunumlar",
        "pros": ["Guclu AI ortak-yazarlik akisi", "Gorsel uretim entegre"],
        "cons": ["Detay duzenlemede PowerPoint kadar esnek degil"],
        "website": "https://tome.app",
    },
    {
        "rank": 4, "name": "Microsoft Copilot for PowerPoint", "score": 8.5,
        "pricing": "Microsoft 365 Copilot eklentisi icinde (kurumsal fiyat)",
        "best_for": "Mevcut PowerPoint is akisina dogrudan entegrasyon",
        "pros": ["Tanidik PowerPoint arayuzu", "Kurumsal veri/dosyalarla calisabilme"],
        "cons": ["Ayri urun degil - M365 Copilot lisansi gerektirir"],
        "website": "https://www.microsoft.com/microsoft-365/copilot",
    },
    {
        "rank": 5, "name": "Canva AI (Magic Design)", "score": 8.4,
        "pricing": "Ucretsiz sinirli + Pro 12-15 $/ay",
        "best_for": "Gorsel agirlikli, sosyal medya uyumlu sunumlar",
        "pros": ["Devasa sablon/gorsel kutuphanesi", "Tasarimla ilgisi olmayanlar icin cok kolay"],
        "cons": ["Veri agirlikli/kurumsal sunumlarda sinirli"],
        "website": "https://www.canva.com",
    },
]

save_comparison(
    slug="ai-sunum-araclari",
    title="En Iyi 5 AI Sunum (Slayt) Araci",
    intro="Metinden veya fikirden hizlica profesyonel sunum uretmek isteyenler icin one cikan "
          "AI destekli sunum araclarini karsilastirdik.",
    items=items,
)

print("Karsilastirma eklendi: /karsilastirma/ai-sunum-araclari")
