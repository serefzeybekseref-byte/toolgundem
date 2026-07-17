# -*- coding: utf-8 -*-
from dotenv import load_dotenv
load_dotenv()
from db import init_db, save_comparison

init_db()

items = [
    {
        "rank": 1, "name": "Suno", "score": 9.3,
        "pricing": "Ucretsiz (gunluk 10 kredi) + Pro 10$/ay + Premier 30$/ay",
        "best_for": "Hizli, kolay, vokalli tam sarki uretimi",
        "pros": ["Saniyeler icinde tam sarki (vokal+enstruman)", "En genis kullanici tabani ve ornek kutuphanesi", "Suno Studio ile stem ayirma (Premier)"],
        "cons": ["Ucretsiz planda ticari haklar yok", "Abonelik iptalinden sonra gecmis sarkilarda geriye donuk ticari hak yok"],
        "website": "https://suno.com",
    },
    {
        "rank": 2, "name": "Udio", "score": 9.0,
        "pricing": "Ucretsiz kredi + Standard 10$/ay",
        "best_for": "Detayli duzenleme ve stem kontrolu isteyenler",
        "pros": ["Guclu remix/uzatma/stem ayirma araclari", "Basit fiyatlandirma yapisi", "Universal/Warner ile lisans anlasmalari mevcut"],
        "cons": ["Ekim 2025'ten beri indirme ozelligi gecici olarak kapali"],
        "website": "https://www.udio.com",
    },
    {
        "rank": 3, "name": "ElevenLabs Music", "score": 8.7,
        "pricing": "Starter plani 6$/ay'dan itibaren (ticari kullanim dahil)",
        "best_for": "Zaten ElevenLabs seslendirme kullanan icerik ureticileri",
        "pros": ["En dusuk giris fiyatiyla ticari kullanim hakki", "ElevenLabs ekosistemiyle entegre calisir"],
        "cons": ["Vokal sarki kalitesinde Suno/Udio kadar one cikmiyor"],
        "website": "https://elevenlabs.io/music",
    },
    {
        "rank": 4, "name": "AIVA", "score": 8.4,
        "pricing": "Ucretsiz sinirli + ucretli planlar (tam telif haklari Pro'da)",
        "best_for": "Klasik/orkestral ve sinematik muzik",
        "pros": ["30.000+ klasik eserle egitildi", "Sinematik/oyun muzigi icin guclu", "Pro planda tam telif sahipligi"],
        "cons": ["Vokal/pop sarki uretiminde Suno/Udio kadar guclu degil"],
        "website": "https://www.aiva.ai",
    },
    {
        "rank": 5, "name": "Stable Audio", "score": 8.0,
        "pricing": "Ucretsiz sinirli + ucretli planlar",
        "best_for": "Ses tasarimi ve enstrumantal alt yapilar",
        "pros": ["Ses tasarimi/instrumental icin guclu", "Lisansli veriyle egitildi"],
        "cons": ["Tam vokal sarki uretiminde diger araclarin gerisinde"],
        "website": "https://stability.ai/stable-audio",
    },
]

save_comparison(
    slug="ai-muzik-uretme-araclari",
    title="Muzik Uretme Icin En Iyi 5 AI Araci",
    intro="2026 itibariyla metinden tam sarki veya enstrumantal muzik ureten en populer AI "
          "araclarini fiyat, ticari haklar ve kullanim kolayligina gore karsilastirdik.",
    items=items,
)

print("Karsilastirma eklendi: /karsilastirma/ai-muzik-uretme-araclari")
