"""
AŞAMA 5: Groq API ile Product Hunt urunleri icin Turkce tanitim metni uretimi.
Model: llama-3.3-70b-versatile (Groq'un hizli ve ucretsiz kotali modeli)
"""
import os
import json
import random
import requests
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"

NVIDIA_NIM_API_KEY = os.getenv("NVIDIA_NIM_API_KEY")
NVIDIA_NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
# qwen3-next-80b-a3b-instruct: qwen3.5-122b-a10b kaldirilmis/adi degismisti (410 Gone hatasi
# verdi), bu 'instruct' varyanti gercek 'content' alani donduruyor (bazi qwen3.5 varyantlari
# 'reasoning' tipinde olup content'i bos birakiyor, dikkat).
NVIDIA_NIM_MODEL = "qwen/qwen3-next-80b-a3b-instruct"


def _call_nvidia_nim(prompt: str, max_tokens: int = 1024) -> dict:
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
        "max_tokens": max_tokens,
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


GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL_TMPL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"


def _call_gemini_raw(prompt: str) -> dict:
    """
    Gemini'ye native REST ile istek atar (deprecated google-generativeai kutuphanesi
    KULLANILMIYOR - AQ. formatli yeni key'lerle sorun cikariyordu). Key havuzunda rotasyon yapar.
    NOT: gemini-2.0-flash bu key'lerde kotasiz (429); gemini-2.5-flash calisiyor.
    """
    if not GEMINI_KEYS:
        raise ValueError("Hic Gemini API key tanimli degil (.env).")

    last_err = None
    for _ in range(len(GEMINI_KEYS)):
        key = GEMINI_KEYS[_gemini_idx["i"] % len(GEMINI_KEYS)]
        _gemini_idx["i"] += 1
        try:
            resp = requests.post(
                GEMINI_URL_TMPL.format(model=GEMINI_MODEL, key=key),
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"response_mime_type": "application/json"},
                },
                timeout=30,
            )
            resp.raise_for_status()
            raw_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            raw_text = raw_text.strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.split("```")[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]
            return json.loads(raw_text.strip())
        except Exception as e:
            last_err = e
            continue
    raise last_err


def _generate_with_fallback(prompt: str, groq_payload_extra: dict, max_tokens: int = 1024) -> dict:
    """
    Groq -> Gemini (5 key rotasyonlu) -> NVIDIA NIM sirasiyla dener. Ilk basarili olan sonucu dondurur.
    Gemini ikinci sirada cunku 5 ayri key'in rotasyonu, tek key'li NIM'e gore cok daha yuksek
    toplam kota/dayaniklilik sagliyor.
    groq_payload_extra: Groq'a ozel ek payload alanlari (temperature, response_format vb.)
    max_tokens: NVIDIA NIM cagrisina iletilir (Groq kendi max_tokens'ini groq_payload_extra
    icinde tasir, Gemini icin ayrica bir token limiti verilmiyor - varsayilan genis).
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
            return _call_nvidia_nim(prompt, max_tokens=max_tokens)
        except Exception as e:
            errors.append(f"NVIDIA NIM: {e}")

    raise RuntimeError("Tum saglayicilar basarisiz oldu -> " + " | ".join(errors))


# Icerik cesitliligini artirmak icin rastgele persona rotasyonu.
# Sadece temperature yukseltmek yerine, her uretimde farkli bir "ses" ile yazdirmak
# ayni urun grubunda (ör. iki video araci) bile farkli anlatim tonlari saglar.
CONTENT_PERSONAS = [
    "Bir teknoloji blog yazarısın. Meraklı ve gündelik bir dille, okuyucuyla sohbet eder gibi yazarsın.",
    "Bir ürün incelemecisisin. Eleştirel ve nesnel bir bakış açın var; hem güçlü hem zayıf yönlere değinirsin.",
    "Bir yazılım geliştiricisin. Teknik detaylara ve pratik kullanım senaryolarına odaklanırsın, jargon kullanmaktan çekinmezsin.",
    "Bir içerik üreticisisin (creator). Aracın günlük iş akışına nasıl zaman kazandırdığını, somut örneklerle anlatırsın.",
    "Bir pazarlama uzmanısın. Aracın hangi iş probleminü çözdüğünü ve kime hitap ettiğini net biçimde ortaya koyarsın.",
]


def generate_turkish_content(product: dict) -> dict:
    """
    Bir Product Hunt urunu icin Turkce baslik, aciklama ve etiketler uretir.
    product: fetch_producthunt.get_latest_products()'tan gelen dict
    Donen: {"title": str, "summary": str, "content": str, "tags": [str]}
    """
    if not GROQ_API_KEY and not GEMINI_KEYS and not NVIDIA_NIM_API_KEY:
        raise ValueError("Hicbir AI saglayici key'i tanimli degil. .env dosyasini kontrol et.")

    persona = random.choice(CONTENT_PERSONAS)

    prompt = f"""Sen {persona} Aşağıdaki Product Hunt ürünü için Türkçe, doğal ve akıcı bir tanıtım içeriği üret. Seçtiğin persona/tona uygun bir üslup ve bakış açısı kullan; bu ürünü senden önce başka bir yazar da anlatmış olabilir, o yüzden kendi bakış açını öne çıkar.

Ürün adı: {product['name']}
İngilizce slogan: {product['tagline']}
İngilizce açıklama: {product.get('description', '')}
Konular: {', '.join(product.get('topics', []))}

Kurallar:
- SADECE ve SADECE Türkçe yaz. Başka hiçbir dilden (İngilizce, İspanyolca, Fransızca vb.) tek bir kelime bile kullanma. Yazdığın her kelimeyi tekrar kontrol et.
- İngilizce'den kelime kelime çeviri yapma, doğal Türkçe ile yeniden yaz.
- SEO'ya uygun, ilgi çekici bir başlık üret (60 karakteri geçmesin).
- 2-3 cümlelik kısa bir özet (summary) üret.
- ÇEŞİTLİLİK ZORUNLU: summary'yi ASLA "[Ürün adı], ... sağlayan/sunan bir araçtır" kalıbıyla başlatma. Bunun yerine rastgele şu tarzlardan birini seç: doğrudan bir eylemle başla ("Sunum hazırlarken saatler harcamak yerine..."), bir soru ile başla, kullanıcının yaşadığı bir sorunla başla, veya çarpıcı bir sonuçla başla. Aynı ürün grubunda (ör. iki video aracı) art arda üretimlerde farklı açılış cümlesi kullan.
- 3-4 paragraflık, okunması akıcı bir tanıtım metni (content) üret. Ürünün ne işe yaradığını, kimler için uygun olduğunu anlat. Şablon hissi vermesin; her ürünün kendine özgü bir yönünü (nişini, en dikkat çekici özelliğini veya kullanım senaryosunu) öne çıkar.
- 3-5 Türkçe etiket (tags) üret (örn: "yapay-zeka", "verimlilik" gibi kısa ve küçük harfli).
- Kimler için uygun olduğunu tek cümlede özetle (why_use_it), örn: "Sunum hazırlamaya vakti olmayan pazarlamacılar ve içerik üreticileri için."
- 3-5 maddelik somut özellik listesi üret (key_features), her biri kısa bir cümle.
- Hangi platformlarda çalıştığını üret (platforms), örn: "Web, iOS, Chrome Eklentisi" (bilmiyorsan "Web" yaz).
- Fiyatlandırma tipini şu seçeneklerden biriyle üret (pricing_type): "Ücretsiz", "Freemium", "Ücretli", "Bilinmiyor".

Yalnızca şu JSON formatında cevap ver, başka hiçbir şey yazma:
{{"title": "...", "summary": "...", "content": "...", "tags": ["...", "..."], "why_use_it": "...", "key_features": ["...", "..."], "platforms": "...", "pricing_type": "..."}}
"""

    # Bilinen yabanci kelime sizintilarina karsi kontrol (Ingilizce/Almanca/Fransizca/Ispanyolca
    # yaygin kelimeler). Kelime siniri (\b) ile eslestirilir ki Turkce kelimelerin icinde
    # rastlantisal alt-dize olarak gecmesin (ornek: "the" kelimesi "kanithe" gibi bir seyde gecmez
    # ama yine de guvenli tarafta kalmak icin sadece bagimsiz kelime olarak arar).
    import re as _re
    # DIKKAT: Turkce ile CAKISAN kelimeler bu listeye eklenmemeli (ornek: "de/da" bağlaç,
    # "can" isim/kelime, "at" (horse), "on" (10 sayisi), "para" (money) - bunlar gercek
    # Turkce cumlelerde surekli gecer ve false-positive/sonsuz retry dongusune sokar.
    SUSPICIOUS_WORDS = [
        # Ingilizce - Turkce ile cakismayan, net yabanci kelimeler
        "thus", "however", "the", "and", "with", "your", "this", "that",
        "will", "now", "successfully", "successful", "were",
        "its", "onto",
        # Almanca
        "erfolgreich", "und", "mit", "für", "das", "die", "der", "ist", "nicht", "auch",
        # Ispanyolca
        "mejores", "que", "con", "los", "las", "una", "esta",
        # Fransizca
        "avec", "pour", "dans",
    ]
    _suspicious_pattern = _re.compile(
        r"\b(" + "|".join(_re.escape(w) for w in SUSPICIOUS_WORDS) + r")\b",
        flags=_re.IGNORECASE,
    )

    def _has_language_leak(result: dict) -> bool:
        full_text = " ".join([
            result.get("title", ""), result.get("summary", ""), result.get("content", ""),
            result.get("why_use_it", ""),
            " ".join(result.get("key_features", [])) if isinstance(result.get("key_features"), list) else str(result.get("key_features", "")),
        ])
        return bool(_suspicious_pattern.search(full_text))

    groq_extra = {"temperature": 0.75, "response_format": {"type": "json_object"}}

    result = _generate_with_fallback(prompt, groq_extra)
    attempts = 1
    while _has_language_leak(result) and attempts < 3:
        result = _generate_with_fallback(prompt, groq_extra)
        attempts += 1
    if _has_language_leak(result):
        # Uc denemede de temizlenemedi - pipeline'in loglayabilmesi icin isaretle.
        result["_language_warning"] = True
        print(f"UYARI: '{product.get('name')}' icin 3 denemede de yabanci kelime sizintisi temizlenemedi.")

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
