"""
AŞAMA 5: Groq API ile Product Hunt urunleri icin Turkce tanitim metni uretimi.
Model: llama-3.3-70b-versatile (Groq'un hizli ve ucretsiz kotali modeli)
"""
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"


def generate_turkish_content(product: dict) -> dict:
    """
    Bir Product Hunt urunu icin Turkce baslik, aciklama ve etiketler uretir.
    product: fetch_producthunt.get_latest_products()'tan gelen dict
    Donen: {"title": str, "summary": str, "content": str, "tags": [str]}
    """
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY bulunamadi. .env dosyasini kontrol et.")

    prompt = f"""Sen bir teknoloji blog yazarısın. Aşağıdaki Product Hunt ürünü için Türkçe, doğal ve akıcı bir tanıtım içeriği üret.

Ürün adı: {product['name']}
İngilizce slogan: {product['tagline']}
İngilizce açıklama: {product.get('description', '')}
Konular: {', '.join(product.get('topics', []))}

Kurallar:
- SADECE ve SADECE Türkçe yaz. Başka hiçbir dilden (İngilizce, İspanyolca, Fransızca vb.) tek bir kelime bile kullanma. Yazdığın her kelimeyi tekrar kontrol et.
- İngilizce'den kelime kelime çeviri yapma, doğal Türkçe ile yeniden yaz.
- SEO'ya uygun, ilgi çekici bir başlık üret (60 karakteri geçmesin).
- 2-3 cümlelik kısa bir özet (summary) üret.
- 3-4 paragraflık, okunması akıcı bir tanıtım metni (content) üret. Ürünün ne işe yaradığını, kimler için uygun olduğunu anlat.
- 3-5 Türkçe etiket (tags) üret (örn: "yapay-zeka", "verimlilik" gibi kısa ve küçük harfli).

Yalnızca şu JSON formatında cevap ver, başka hiçbir şey yazma:
{{"title": "...", "summary": "...", "content": "...", "tags": ["...", "..."]}}
"""

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
        "response_format": {"type": "json_object"},
    }

    def _call_groq():
        resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        raw_text = resp.json()["choices"][0]["message"]["content"]
        return json.loads(raw_text)

    # Bilinen yabanci kelime sizintilarina karsi basit bir kontrol.
    # Bulursa bir kere daha dener (modelin rastgeleligi degisebilir).
    suspicious_words = ["thus", "however", "mejores", "the ", " and ", "que ", "para "]

    result = _call_groq()
    full_text = (result.get("title", "") + " " + result.get("summary", "") + " " + result.get("content", "")).lower()
    if any(w in full_text for w in suspicious_words):
        result = _call_groq()  # ikinci deneme

    return result


if __name__ == "__main__":
    # Hizli test icin sahte bir urun
    test_product = {
        "name": "Zro",
        "tagline": "Private inference for coding agents",
        "description": "Zro provides private, secure inference infrastructure for AI coding agents.",
        "topics": ["API", "Developer Tools", "Tech"],
    }
    result = generate_turkish_content(test_product)
    print(json.dumps(result, ensure_ascii=False, indent=2))
