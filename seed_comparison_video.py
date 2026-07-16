# -*- coding: utf-8 -*-
from db import init_db, save_comparison

init_db()

items = [
    {
        "rank": 1, "name": "Google Veo 3.1", "score": 9.3,
        "pricing": "Gemini uygulamasi icinde sinirli ucretsiz + Google AI Pro/Ultra planlari",
        "best_for": "Senkron ses/diyalog ile sinematik, gercekci klipler",
        "pros": ["48kHz native ses uretimi", "Guclu prompt takibi", "Google ekosistemiyle entegre"],
        "cons": ["Yogun kullanimda kredi tuketimi hizli", "Tum bolgelerde ayni fiyat degil"],
        "website": "https://deepmind.google/technologies/veo/",
    },
    {
        "rank": 2, "name": "Kling 3.0", "score": 9.0,
        "pricing": "Ucretsiz gunluk deneme + ~0.10$/saniye (kredi bazli)",
        "best_for": "Yuksek hareketli sahneler, coklu dilde dudak senkronu",
        "pros": ["En ucuz premium secenek", "4K cikti", "Coklu dil dudak senkronu"],
        "cons": ["Uzun sekanslarda tutarlilik Runway kadar guclu degil"],
        "website": "https://klingai.com",
    },
    {
        "rank": 3, "name": "Runway Gen-4.5", "score": 8.8,
        "pricing": "Standart 12-15$/ay, Unlimited 76-95$/ay",
        "best_for": "Kamera kontrolu, video-to-video, profesyonel kurgu is akisi",
        "pros": ["En iyi kontrol yuzeyi (keyframe, motion brush)", "Film produksiyon ekosistemi", "Video duzenleme entegre"],
        "cons": ["Saf gorsel kalite siralamasinda ust siralardan dustu", "Kredi sistemi karisik olabilir"],
        "website": "https://runwayml.com",
    },
    {
        "rank": 4, "name": "Seedance 2.0", "score": 8.6,
        "pricing": "API bazli, dusuk maliyetli (saniye basi ucretlendirme)",
        "best_for": "Gorsel kalite/performans dengesi arayan gelistiriciler",
        "pros": ["Artificial Analysis liderlik tablosunda ust siralar", "Uygun API fiyati"],
        "cons": ["Hazir tuketici arayuzu sinirli", "Marka bilinirligi dusuk"],
        "website": "https://seed.bytedance.com",
    },
    {
        "rank": 5, "name": "Luma Dream Machine (Ray 3)", "score": 8.3,
        "pricing": "Ucretsiz sinirli + 9.99$/ay'dan baslayan planlar",
        "best_for": "Gorselden video, derinlik/hacim onemliyse",
        "pros": ["Goruntuden videoya guclu donusum", "Kolay arayuz"],
        "cons": ["Sinematik hareket kalitesi liderlerin gerisinde"],
        "website": "https://lumalabs.ai",
    },
]

save_comparison(
    slug="video-ureten-ai-araclari",
    title="Metinden Video Ureten En Iyi 5 AI Araci",
    intro="2026 ortasi itibariyla aktif kullanilabilen video uretim modellerini gercekcilik, "
          "kontrol, fiyat ve is akisi uyumuna gore karsilastirdik. (Not: OpenAI Sora, Nisan 2026'da "
          "kullanimdan kaldirildigi icin bu listeye alinmadi.)",
    items=items,
)

print("Karsilastirma eklendi: /karsilastirma/video-ureten-ai-araclari")
