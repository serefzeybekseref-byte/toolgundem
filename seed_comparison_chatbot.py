# -*- coding: utf-8 -*-
from db import init_db, save_comparison

init_db()

items = [
    {
        "rank": 1, "name": "Claude", "score": 9.3,
        "pricing": "Ucretsiz sinirli + Pro 20 $/ay, Max planlar",
        "best_for": "Uzun belge analizi, yazma, kodlama, guvenilirlik",
        "pros": ["Genis baglam penceresi", "Dogal, az 'yapay' hisseden yazim", "Guclu dosya/artifact uretimi"],
        "cons": ["Gorsel/ses uretimi native degil", "Bazi bolgelerde erisim kisitli"],
        "website": "https://claude.ai",
    },
    {
        "rank": 2, "name": "ChatGPT", "score": 9.2,
        "pricing": "Ucretsiz sinirli + Plus 20 $/ay, Pro 200 $/ay",
        "best_for": "Genel amacli kullanim, en genis eklenti/entegrasyon ekosistemi",
        "pros": ["En genis kullanici tabani", "Sesli mod ve gorsel uretim entegre", "Guclu hafiza ozelligi"],
        "cons": ["Yogun saatlerde yavaslama olabiliyor"],
        "website": "https://chatgpt.com",
    },
    {
        "rank": 3, "name": "Gemini", "score": 8.9,
        "pricing": "Ucretsiz sinirli + Google AI Pro/Ultra planlari",
        "best_for": "Google ekosistemiyle entegre calisma (Gmail, Docs, Workspace)",
        "pros": ["Workspace entegrasyonu guclu", "Coklu model (Flash/Pro) secenegi", "Genis baglam penceresi"],
        "cons": ["Yanit tutarliligi bazen degiskenlik gosterebiliyor"],
        "website": "https://gemini.google.com",
    },
    {
        "rank": 4, "name": "Grok", "score": 8.4,
        "pricing": "X Premium icinde + ayri Grok abonelikleri",
        "best_for": "Guncel olaylar, X/Twitter verisiyle baglam",
        "pros": ["Gercek zamanli X verisine erisim", "Daha az kisitlayici ton"],
        "cons": ["Dogruluk/tutarlilik konusunda karisik degerlendirmeler"],
        "website": "https://grok.com",
    },
    {
        "rank": 5, "name": "Perplexity", "score": 8.3,
        "pricing": "Ucretsiz sinirli + Pro 20 $/ay",
        "best_for": "Kaynakli arama/arastirma odakli sorular",
        "pros": ["Her yanitta kaynak gosterimi", "Arastirma/rapor modu guclu"],
        "cons": ["Genel sohbet/yaraticilik acisindan diger araclarin gerisinde"],
        "website": "https://www.perplexity.ai",
    },
]

save_comparison(
    slug="ai-sohbet-botlari",
    title="En Iyi 5 AI Sohbet Asistani",
    intro="Genel amacli AI sohbet asistanlarini kullanim kolayligi, entegrasyon ve guclu "
          "yonlerine gore karsilastirdik.",
    items=items,
)

print("Karsilastirma eklendi: /karsilastirma/ai-sohbet-botlari")
