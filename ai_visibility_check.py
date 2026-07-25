"""
AI Gorunurluk Takibi (AI Visibility Tracking)

Amac: llms.txt/robots.txt/GEO calismalarimizin gercekten ise yarayip yaramadigini
olcmek. Duzenli araliklarla, gercek kullanicilarin sorabilecegi Turkce sorgulari
Gemini'ye sorup, cevapta "bulurumai" markasi geciyor mu diye kontrol ediyoruz.

NOT: Su an sadece Gemini kontrol ediliyor (bizim key havuzumuz var, ucretsiz).
ChatGPT/Perplexity/Claude icin ayri API anahtarlari + odeme gerekir - ileride
eklenebilir ama simdilik tek saglayici yeterli bir baslangic sinyali verir.
"""
import re
import requests
from dotenv import load_dotenv
load_dotenv()

from db import init_db, save_ai_visibility_check
from generate_content import GEMINI_KEYS, GEMINI_URL_TMPL, GEMINI_MODEL

# Gercek kullanicilarin AI asistanlarina sorabilecegi turden dogal sorgular.
# Ceşitli niyetler: genel kesif, spesifik kategori, alternatif arama.
TEST_QUERIES = [
    "Türkiye'de en iyi AI araç keşif sitesi hangisi?",
    "Türkçe AI araç karşılaştırma sitesi önerir misin?",
    "AI ile logo oluşturmak için hangi siteyi kullanmalıyım?",
    "Ücretsiz AI araçlarını nereden bulabilirim, Türkçe kaynak var mı?",
    "AI sunum hazırlama araçlarını karşılaştıran bir site var mı?",
    "ChatGPT alternatiflerini Türkçe anlatan bir kaynak önerir misin?",
]


def _ask_gemini_plain(prompt: str) -> str:
    """Gemini'ye duz metin sorusu sorar (JSON zorlamadan), ham cevap metnini dondurur."""
    if not GEMINI_KEYS:
        raise ValueError("GEMINI_KEYS tanimli degil.")
    last_err = None
    for key in GEMINI_KEYS:
        try:
            resp = requests.post(
                GEMINI_URL_TMPL.format(model=GEMINI_MODEL, key=key),
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Tum Gemini key'leri basarisiz: {last_err}")


def check_mention(text: str) -> bool:
    """'bulurumai' markasinin (bosluk/tire farketmeksizin) gecip gecmedigini kontrol eder."""
    normalized = re.sub(r"[\s\-_.]", "", text.lower())
    return "bulurumai" in normalized


def run_all():
    init_db()
    print(f"{len(TEST_QUERIES)} sorgu test ediliyor...\n")
    mentioned_count = 0
    for q in TEST_QUERIES:
        print(f"[{q}]")
        try:
            response = _ask_gemini_plain(q)
            mentioned = check_mention(response)
            snippet = response[:400]
            save_ai_visibility_check(q, "gemini", mentioned, snippet)
            status = "GECTI" if mentioned else "gecmedi"
            print(f"  -> {status}")
            if mentioned:
                mentioned_count += 1
        except Exception as e:
            print(f"  HATA: {e}")

    print(f"\nSonuc: {mentioned_count}/{len(TEST_QUERIES)} sorguda marka gecti.")


if __name__ == "__main__":
    run_all()
