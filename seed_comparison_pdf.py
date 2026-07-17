# -*- coding: utf-8 -*-
from dotenv import load_dotenv
load_dotenv()
from db import init_db, save_comparison

init_db()

items = [
    {
        "rank": 1, "name": "ChatPDF", "score": 8.9,
        "pricing": "Ucretsiz (gunde 2 PDF, kayit gerektirmez) + Plus 5$/ay",
        "best_for": "Hizli, tek dosyalik soru-cevap, sifir kurulum",
        "pros": ["Kayit gerektirmeden aninda kullanim", "Sayfa numarali kaynak gosterimi", "En dusuk giris engeli"],
        "cons": ["Ucretsiz planda gunluk 2 PDF ve 120 sayfa siniri"],
        "website": "https://www.chatpdf.com",
    },
    {
        "rank": 2, "name": "Google NotebookLM", "score": 8.8,
        "pricing": "Tamamen ucretsiz",
        "best_for": "Coklu kaynak arastirma, sesli ozet (podcast tarzi)",
        "pros": ["Tamamen ucretsiz", "Birden fazla PDF'i ayni anda analiz edebilir", "PDF'leri sesli podcast diyaloguna cevirebiliyor"],
        "cons": ["Google hesabi gerektirir", "Cok ozel/teknik dokumanlar icin sinirli ozellesme"],
        "website": "https://notebooklm.google.com",
    },
    {
        "rank": 3, "name": "Smallpdf", "score": 8.5,
        "pricing": "Ucretsiz sinirli + 10$/ay (AI dahil tam paket)",
        "best_for": "PDF sikistirma/donusturme + AI sohbetini tek yerde isteyenler",
        "pros": ["30+ PDF araci (sikistirma, birlestirme, imzalama) + AI bir arada", "Gunluk PDF isleriyle ugrasanlar icin pratik"],
        "cons": ["AI derinligi ChatPDF/AskYourPDF kadar ozellesmis degil"],
        "website": "https://smallpdf.com",
    },
    {
        "rank": 4, "name": "AskYourPDF", "score": 8.2,
        "pricing": "Ucretsiz sinirli + Premium 11.99$/ay",
        "best_for": "Birden fazla AI modelini (GPT-5, Claude, Gemini) karsilastirmak isteyenler",
        "pros": ["GPT-5, Claude 4.5, Gemini 2.5 arasinda model secimi", "Bilgi tabani ile coklu dokuman sohbeti (Premium)"],
        "cons": ["Bazi kullanicilar fatura/iptal surecinde sorun bildirdi, dikkatli okunmali"],
        "website": "https://askyourpdf.com",
    },
    {
        "rank": 5, "name": "Humata AI", "score": 8.0,
        "pricing": "Ucretsiz sinirli + Ogrenci plani 1.99$/ay (.edu mail ile)",
        "best_for": "Butcesi kisitli ogrenciler",
        "pros": ["Kategorideki en ucuz ucretli plan (ogrenciler icin)", "Ayda 200 sayfaya kadar erisim"],
        "cons": ["Ogrenci disi kullanicilar icin fiyat avantaji yok"],
        "website": "https://www.humata.ai",
    },
]

save_comparison(
    slug="ai-pdf-araclari",
    title="PDF ile Sohbet ve Ozetleme Icin En Iyi 5 AI Araci",
    intro="2026 itibariyla uzun PDF dokumanlarini ozetlemek, sorgulamak ve analiz etmek icin "
          "en cok tercih edilen AI araclarini fiyat ve kullanim kolayligina gore karsilastirdik.",
    items=items,
)

print("Karsilastirma eklendi: /karsilastirma/ai-pdf-araclari")
