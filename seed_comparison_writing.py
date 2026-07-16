# -*- coding: utf-8 -*-
from db import init_db, save_comparison

init_db()

items = [
    {
        "rank": 1, "name": "Jasper", "score": 8.9,
        "pricing": "Creator 49 $/ay, Pro 69 $/ay, Business ozel fiyat",
        "best_for": "Marka sesi tutarliligiyla kurumsal pazarlama metni",
        "pros": ["Marka sesi/stil hafizasi", "Ekip is akisi araclari", "SEO entegrasyonlari"],
        "cons": ["Fiyat rakiplerine gore yuksek", "Serbest yazarlar icin agir kalabiliyor"],
        "website": "https://www.jasper.ai",
    },
    {
        "rank": 2, "name": "Copy.ai", "score": 8.5,
        "pricing": "Ucretsiz sinirli + Pro 49 $/ay",
        "best_for": "Pazarlama otomasyonu ve is akisi tabanli icerik",
        "pros": ["Is akisi/otomasyon sablonlari", "Uygun giris fiyati"],
        "cons": ["Uzun form icerikte Jasper kadar detayli degil"],
        "website": "https://www.copy.ai",
    },
    {
        "rank": 3, "name": "Grammarly", "score": 8.7,
        "pricing": "Ucretsiz sinirli + Premium 12-30 $/ay",
        "best_for": "Dilbilgisi, ton duzenleme, mevcut metni iyilestirme",
        "pros": ["Her yerde calisan tarayici eklentisi", "Guclu ton/aciklik onerileri"],
        "cons": ["Sifirdan uzun icerik uretmede zayif"],
        "website": "https://www.grammarly.com",
    },
    {
        "rank": 4, "name": "Sudowrite", "score": 8.3,
        "pricing": "10-44 $/ay arasi planlar",
        "best_for": "Kurgu/roman yazarlari icin yaratici yazim",
        "pros": ["Hikaye tutarliligi araclari", "Yaratici yazarlar icin ozellesmis"],
        "cons": ["Pazarlama/is metni icin uygun degil"],
        "website": "https://www.sudowrite.com",
    },
    {
        "rank": 5, "name": "Writesonic", "score": 8.1,
        "pricing": "Ucretsiz sinirli + 19-99 $/ay",
        "best_for": "SEO odakli blog ve makale uretimi",
        "pros": ["Entegre SEO analiz araclari", "Toplu makale uretimi"],
        "cons": ["Cikti kalitesi bazen ek duzenleme gerektiriyor"],
        "website": "https://writesonic.com",
    },
]

save_comparison(
    slug="ai-yazi-araclari",
    title="En Iyi 5 AI Yazi ve Icerik Uretim Araci",
    intro="Pazarlama metninden kurgu yazarligina kadar farkli yazim ihtiyaclarina gore "
          "one cikan AI yazi araclarini karsilastirdik.",
    items=items,
)

print("Karsilastirma eklendi: /karsilastirma/ai-yazi-araclari")
