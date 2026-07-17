# -*- coding: utf-8 -*-
from dotenv import load_dotenv
load_dotenv()
from db import init_db, save_comparison

init_db()

items = [
    {
        "rank": 1, "name": "Looka", "score": 8.9,
        "pricing": "Tasarim ucretsiz + Basic 20$ (tek seferlik) + Premium 65$ + Brand Kit 96$/yil",
        "best_for": "Kapsamli marka kiti isteyenler (kartvizit, sosyal medya sablonlari)",
        "pros": ["14.000+ Trustpilot yorumuyla en cok degerlendirilen arac", "Genis marka kiti (300+ sablon)", "Kolay ve hizli sihirbaz akisi"],
        "cons": ["Vektor (SVG) dosyasi icin Premium pakete gecmek gerekiyor", "Suruklet-birak duzenleme yok"],
        "website": "https://looka.com",
    },
    {
        "rank": 2, "name": "Design.com", "score": 8.7,
        "pricing": "Ucretsiz sinirli + ucretli paketler",
        "best_for": "Logodan oteye gecip tam marka kimligi olusturmak isteyenler",
        "pros": ["50'den fazla markalama araci tek platformda", "Genis logo kutuphanesi", "Web sitesi, kartvizit gibi ek urunlere kolay genisleme"],
        "cons": ["Cok fazla ozellik yeni kullanicilar icin karmasik olabilir"],
        "website": "https://www.design.com",
    },
    {
        "rank": 3, "name": "Tailor Brands", "score": 8.3,
        "pricing": "Sadece abonelik: 48$/yil (temel) - 72$/yil (SVG dahil)",
        "best_for": "Logo + sirket kurulusu (LLC) + domain'i birlikte halletmek isteyenler",
        "pros": ["Detayli soru formu ile daha kisisellestirilmis sonuclar", "4.7/5 Trustpilot puani", "LLC kurulumu gibi ek is hizmetleri"],
        "cons": ["Ucretsiz/tek seferlik secenek yok, sadece abonelik"],
        "website": "https://www.tailorbrands.com",
    },
    {
        "rank": 4, "name": "Brandmark.io", "score": 8.1,
        "pricing": "Ucretsiz sinirli + ucretli paketler (Enterprise'a kadar 195$)",
        "best_for": "Daha benzersiz/ayirt edici sonuc arayan kurumsal kullanicilar",
        "pros": ["Ust seviye paketlerde insan tasarimci destegi", "Daha ozgun/az sablon hissi veren ciktilar"],
        "cons": ["En ust katmanlar pahali (195$'a kadar)"],
        "website": "https://brandmark.io",
    },
    {
        "rank": 5, "name": "Shopify Logo Maker", "score": 7.8,
        "pricing": "Tamamen ucretsiz",
        "best_for": "Butcesi olmayan, hizli ve basit bir logoya ihtiyaci olanlar",
        "pros": ["Tamamen ucretsiz, PNG ve SVG indirme", "Kayit/abonelik gerektirmiyor"],
        "cons": ["Agirlikli olarak sablon tabanli, ozgunluk sinirli"],
        "website": "https://www.shopify.com/tools/logo-maker",
    },
]

save_comparison(
    slug="ai-logo-tasarim-araclari",
    title="Logo Tasarimi Icin En Iyi 5 AI Araci",
    intro="2026 itibariyla kucuk isletmeler ve girisimcilerin en cok tercih ettigi AI logo "
          "olusturma araclarini fiyat, marka kiti kapsami ve dosya formatlarina gore karsilastirdik.",
    items=items,
)

print("Karsilastirma eklendi: /karsilastirma/ai-logo-tasarim-araclari")
