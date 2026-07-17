# -*- coding: utf-8 -*-
from dotenv import load_dotenv
load_dotenv()
from db import init_db, save_comparison

init_db()

items = [
    {
        "rank": 1, "name": "Kickresume", "score": 9.0,
        "pricing": "Ucretsiz (4 sablon, AI yok) + Yillik 4.50$/ay + Aylik 19$/ay",
        "best_for": "Guclu AI yazim kalitesi ve sablon cesitliligi arayanlar",
        "pros": ["GPT-4 destekli guclu ilk taslak yazimi", "40+ ATS uyumlu sablon", "Kisisel web sitesi sablonlari dahil"],
        "cons": ["Ucretsiz planda AI Writer yok"],
        "website": "https://www.kickresume.com",
    },
    {
        "rank": 2, "name": "Teal", "score": 8.8,
        "pricing": "Ucretsiz (sinirsiz ozgecmis + takip) + ucretli katmanlar",
        "best_for": "Is takibiyle birlikte tum surecin yonetimi",
        "pros": ["En comert ucretsiz plan (sinirsiz ozgecmis + is takibi)", "Ozgecmis + is arama takibini birlestiriyor"],
        "cons": ["Sadece ozgecmis ozellikleri tek basina fiyati hak etmeyebilir"],
        "website": "https://www.tealhq.com",
    },
    {
        "rank": 3, "name": "Rezi", "score": 8.6,
        "pricing": "Ucretsiz sinirli + 149$ omur boyu lisans",
        "best_for": "Uzun vadede tekrar tekrar kullanacaklar",
        "pros": ["Gercek zamanli ATS anahtar kelime skorlama", "23 puanlik optimizasyon kriteri", "Omur boyu lisans secenegi"],
        "cons": ["Tasarim sablonlari Kickresume/Enhancv kadar polished degil"],
        "website": "https://www.rezi.ai",
    },
    {
        "rank": 4, "name": "Jobscan", "score": 8.3,
        "pricing": "Ayda 5 ucretsiz tarama + 49.95$/ay",
        "best_for": "Sadece ATS anahtar kelime eslesme analizi",
        "pros": ["En detayli anahtar kelime raporu", "Is ilaniyla dogrudan karsilastirma"],
        "cons": ["Bir ozgecmis olusturucu degil, sadece tarayici", "Kategorideki en pahali secenek"],
        "website": "https://www.jobscan.co",
    },
    {
        "rank": 5, "name": "Enhancv", "score": 8.1,
        "pricing": "Ucretsiz sinirli + 24.99$/ay",
        "best_for": "Gorsel olarak en cok one cikan tasarim isteyenler",
        "pros": ["En polished/gorsel arayuz", "17 kriterli icerik analizoru", "Kapak mektubu da uretiyor"],
        "cons": ["Fiyat kategori ortalamasinin ustunde"],
        "website": "https://enhancv.com",
    },
]

save_comparison(
    slug="ai-ozgecmis-hazirlama-araclari",
    title="Ozgecmis (CV) Hazirlama Icin En Iyi 5 AI Araci",
    intro="2026 itibariyla is arayanlarin en cok tercih ettigi AI ozgecmis olusturma ve ATS "
          "optimizasyon araclarini fiyat ve ozellik acisindan karsilastirdik.",
    items=items,
)

print("Karsilastirma eklendi: /karsilastirma/ai-ozgecmis-hazirlama-araclari")
