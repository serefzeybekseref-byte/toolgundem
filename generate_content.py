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

NVIDIA_NIM_API_KEY = os.getenv("NVIDIA_NIM_API_KEY")
NVIDIA_NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_NIM_MODEL = "meta/llama-3.3-70b-instruct"


def _call_nvidia_nim(prompt: str) -> dict:
    """NVIDIA NIM (OpenAI-uyumlu) ile ayni prompt'u calistirir, JSON dondurur."""
    if not NVIDIA_NIM_API_KEY:
        raise ValueError("NVIDIA_NIM_API_KEY tanimli degil (.env).")
    headers = {
        "Authorization": f"Bearer {NVIDIA_NIM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": NVIDIA_NIM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
        "max_tokens": 1024,
    }
    resp = requests.post(NVIDIA_NIM_URL, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    raw_text = resp.json()["choices"][0]["message"]["content"]
    # Model bazen JSON'u kod bloguna sarabilir, temizle.
    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
    return json.loads(raw_text.strip())

# Groq kotasi dolduğunda (429) devreye giren Gemini yedek key havuzu.
GEMINI_KEYS = [
    v for k, v in sorted(os.environ.items())
    if k.startswith("GEMINI_API_KEY") and v
]
_gemini_idx = {"i": 0}


def _call_gemini_raw(prompt: str) -> dict:
    """Gemini ile ayni prompt'u calistirir, JSON dondurur. Key havuzunda rotasyon yapar."""
    import google.generativeai as genai

    if not GEMINI_KEYS:
        raise ValueError("Hic Gemini API key tanimli degil (.env).")

    last_err = None
    for _ in range(len(GEMINI_KEYS)):
        key = GEMINI_KEYS[_gemini_idx["i"] % len(GEMINI_KEYS)]
        _gemini_idx["i"] += 1
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel(
                "gemini-2.0-flash",
                generation_config={"response_mime_type": "application/json"},
            )
            resp = model.generate_content(prompt)
            return json.loads(resp.text)
        except Exception as e:
            last_err = e
            continue
    raise last_err


def _generate_with_fallback(prompt: str, groq_payload_extra: dict) -> dict:
    """
    Groq -> Gemini -> NVIDIA NIM sirasiyla dener. Ilk basarili olan sonucu dondurur.
    groq_payload_extra: Groq'a ozel ek payload alanlari (temperature, response_format vb.)
    """
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        **groq_payload_extra,
    }

    errors = []

    if GROQ_API_KEY:
        try:
            resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            return json.loads(resp.json()["choices"][0]["message"]["content"])
        except Exception as e:
            errors.append(f"Groq: {e}")

    if GEMINI_KEYS:
        try:
            return _call_gemini_raw(prompt)
        except Exception as e:
            errors.append(f"Gemini: {e}")

    if NVIDIA_NIM_API_KEY:
        try:
            return _call_nvidia_nim(prompt)
        except Exception as e:
            errors.append(f"NVIDIA NIM: {e}")

    raise RuntimeError("Tum saglayicilar basarisiz oldu -> " + " | ".join(errors))


def generate_turkish_content(product: dict) -> dict:
    """
    Bir Product Hunt urunu icin Turkce baslik, aciklama ve etiketler uretir.
    product: fetch_producthunt.get_latest_products()'tan gelen dict
    Donen: {"title": str, "summary": str, "content": str, "tags": [str]}
    """
    if not GROQ_API_KEY and not GEMINI_KEYS and not NVIDIA_NIM_API_KEY:
        raise ValueError("Hicbir AI saglayici key'i tanimli degil. .env dosyasini kontrol et.")

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
- Kimler için uygun olduğunu tek cümlede özetle (why_use_it), örn: "Sunum hazırlamaya vakti olmayan pazarlamacılar ve içerik üreticileri için."
- 3-5 maddelik somut özellik listesi üret (key_features), her biri kısa bir cümle.
- Hangi platformlarda çalıştığını üret (platforms), örn: "Web, iOS, Chrome Eklentisi" (bilmiyorsan "Web" yaz).
- Fiyatlandırma tipini şu seçeneklerden biriyle üret (pricing_type): "Ücretsiz", "Freemium", "Ücretli", "Bilinmiyor".

Yalnızca şu JSON formatında cevap ver, başka hiçbir şey yazma:
{{"title": "...", "summary": "...", "content": "...", "tags": ["...", "..."], "why_use_it": "...", "key_features": ["...", "..."], "platforms": "...", "pricing_type": "..."}}
"""

    # Bilinen yabanci kelime sizintilarina karsi basit bir kontrol.
    # Bulursa bir kere daha dener (modelin rastgeleligi degisebilir).
    suspicious_words = ["thus", "however", "mejores", "the ", " and ", "que ", "para "]
    groq_extra = {"temperature": 0.4, "response_format": {"type": "json_object"}}

    result = _generate_with_fallback(prompt, groq_extra)
    full_text = (result.get("title", "") + " " + result.get("summary", "") + " " + result.get("content", "")).lower()
    if any(w in full_text for w in suspicious_words):
        result = _generate_with_fallback(prompt, groq_extra)  # ikinci deneme

    return result


def generate_quickfacts(product_row: dict) -> dict:
    """
    Var olan (Turkce icerigi zaten uretilmis) bir urun icin eksik
    why_use_it/key_features/platforms/pricing_type alanlarini uretir.
    product_row: db'den gelen mevcut urun satiri (original_name, summary_tr, content_tr, tags, topics)
    """
    if not GROQ_API_KEY and not GEMINI_KEYS and not NVIDIA_NIM_API_KEY:
        raise ValueError("Hicbir AI saglayici key'i tanimli degil. .env dosyasini kontrol et.")

    prompt = f"""Sen bir teknoloji editörüsün. Aşağıdaki AI aracı için, var olan Türkçe içeriğe dayanarak
4 ek bilgi alanı üret. Yeni bilgi uydurma; sadece verilen metinden çıkarım yap, emin değilsen makul bir varsayım kullan.

Ürün adı: {product_row.get('original_name', '')}
Özet: {product_row.get('summary_tr', '')}
İçerik: {product_row.get('content_tr', '')}
Etiketler: {product_row.get('tags', '')}
Konular: {product_row.get('topics', '')}

Kurallar:
- SADECE Türkçe yaz.
- why_use_it: Kimler için uygun olduğunu tek cümlede özetle.
- key_features: 3-5 maddelik somut özellik listesi (liste/array olarak).
- platforms: Muhtemel platform(lar) — örn "Web" (bilmiyorsan sadece "Web" yaz).
- pricing_type: "Ücretsiz", "Freemium", "Ücretli" veya "Bilinmiyor" seçeneklerinden biri.

Yalnızca şu JSON formatında cevap ver:
{{"why_use_it": "...", "key_features": ["...", "..."], "platforms": "...", "pricing_type": "..."}}
"""

    groq_extra = {"temperature": 0.3, "response_format": {"type": "json_object"}}
    return _generate_with_fallback(prompt, groq_extra)


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
