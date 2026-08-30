#!/usr/bin/env python3
"""Evergreen içerik oluşturma scripti - Groq API kullanarak"""
import os
import json
import sys
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    print("❌ GROQ_API_KEY .env dosyasında bulunamadı!")
    sys.exit(1)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-20b"

# 15 evergreen konu başlığı
EVERGREEN_TOPICS = [
    "AI araçlarıyla yazgelimi nasıl artırırsınız",
    "Yapay zeka ile tasarım hızlandırma",
    "AI fotoğraf düzenleyiciler karşılaştırması",
    "ChatGPT vs Claude vs Gemini: hangi seçilir",
    "AI ile programlama öğrenme yolları",
    "Yapay zeka ile e-ticaret optimizasyonu",
    "AI ses araçları ve kullanım alanları",
    "AI video üretimi başlangıç rehberi",
    "AI showsızlying algılama araçları",
    "Kurumsal AI uygulamaları küçük işletmeler için",
    "AI ile zaman yönetimi ve produktivite",
    "Yapay zeka riskleri ve etik konuları",
    "AI destekli rehber ve planlayıcı araçlar",
    "AI ile dijital pazarlama otomatasyonu",
    "AI güvenlik ve privacy araçları"
]

EVERGREEN_PROMPT_TEMPLATE = """
Sen deneyimli bir AI araç incelemen ve içerik yazarısın. Aşağıdaki konuyu Türkçe olarak 600-800 kelime arasında, detaylı, orijinal ve değerli bir inceleme yap.

KONU: {topic}

Şunları içermelisin:
1. Giriş: Konun önemli olduğunu ve okuyucunun ihtiyaç duyduğunu anlat
2. Detaylı açıklama: Konu nedir, nasıl çalışır, özellikleri
3. En iyi araç/uygulama: Hang AI araçları bu konuyu destekler?
4. Kullanım senaryoları: Gerçek hayat örnekleri (3-4 örnek)
5. Avantaj/dezavantaj: Dikkatli bir inceleme olmalı
6. Sonuç/Değerlendirme: Okuyucuya ne önerisi var?
7. Yazar bilgi: "Seref (BulurumAI Team)" olarak bit

SEO uyumlu olsun: Anahtar kelime kullan, başlık (H1), altyapı (H2, H3) kullan.
Cümle uzunluğu vary edici olsun. Türkçe dil bilgisi hatası olmadan yaz.
Çok kısalık (1-2 cümle) alt paragraflar olmaz. Her paragraf en az 3-5 cümledir.
"""

def call_groq(prompt):
    """Groq API'sine istek gönder"""
    import requests
    
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.5,
        "max_tokens": 1500,
    }
    
    try:
        resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"❌ Groq API hatası: {e}")
        return None

def generate_evergreen_content():
    """Tüm evergreen içerikleri oluştur"""
    generated = 0
    import re
    
    for i, topic in enumerate(EVERGREEN_TOPICS, 1):
        print(f"🔄 [{i}/{len(EVERGREEN_TOPICS)}] Oluşturuluyor: {topic}")
        prompt = EVERGREEN_PROMPT_TEMPLATE.format(topic=topic)
        content = call_groq(prompt)
        
        if content:
            # Basit dosya adı oluştur - sadece kelime aralayarak
            safe_title = re.sub(r'[^\w\s-]', '', topic).strip().lower()
            safe_title = re.sub(r'\s+', '-', safe_title)
            filename = f"content/evergreen-{i}-{safe_title}.md"
            
            # Klasör var mı kontrol et
            os.makedirs("content", exist_ok=True)
            
            # Dosyaya kaydet
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"# {topic}\n\n")
                f.write(content)
            
            print(f"   ✅ Kaydedildi: {filename}")
            generated += 1
        else:
            print(f"   ⚠️  {topic} için içerik oluşturulamadı")
    
    print(f"\n📊 Toplam {generated}/{len(EVERGREEN_TOPICS)} evergreen içerik oluşturuldu")
    return generated

if __name__ == "__main__":
    generate_evergreen_content()