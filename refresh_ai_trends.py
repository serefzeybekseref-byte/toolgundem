# -*- coding: utf-8 -*-
"""
NVIDIA NIM (LLM) + Web Search (DuckDuckGo/ddgs) kullanarak her gün canlı AI haberlerini,
trendlerini ve sosyal medyada viral olan araçları tarar, ozetler ve ai_trends tablosuna yazar.
"""
import os
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from nim_tools import call_nim_with_search
from db import init_db, save_ai_trend, get_latest_ai_trends, find_internal_slug_for_trend


def fetch_latest_ai_trends():
    init_db()
    print("[NIM Trend Radar] Canli web aramasiyla gunun AI trendleri taraniyor...")

    prompt = """
Web araması (web_search) aracını kullanarak, tanınmış/popüler bir AI aracının (ChatGPT,
Claude, Gemini, Midjourney, Canva, Notion, Perplexity, ElevenLabs, Runway, Grammarly gibi
çok bilinen, yaygın kullanılan araçlardan biri — küçük/bilinmeyen yeni lansmanlar DEĞİL)
son birkaç gündeki somut bir güncelleme/özellik haberini bul. 3 farklı tanınmış araç için
ayrı ayrı ara.

ÖNEMLİ KURALLAR:
- "AI Araçları 2026" gibi genel/soyut başlık UYDURMA — her başlıkta MUTLAKA yukarıdaki
  gibi tanınmış, gerçek bir araç ismi geçmeli.
- SADECE düzgün, eksiksiz Türkçe yaz. Türkçe'ye özgü harfleri (ı, ğ, ü, ş, ö, ç) MUTLAKA
  doğru kullan — "gelistirdi" değil "geliştirdi", "ozellik" değil "özellik", "duzeltti"
  değil "düzeltti" yaz. Türkçe karakterleri ASCII'ye (i, g, u, s, o, c) indirgeme.
- Hiçbir İngilizce kelime kullanma.

Bize TAM OLARAK aşağıdaki JSON formatında bir yanıt ver. Başka hiçbir giriş veya açıklama yazma, SADECE geçerli bir JSON array döndür:

[
  {
    "title": "Tanınmış araç ismi geçen, spesifik gelişme başlığı (düzgün Türkçe, max 60 karakter)",
    "summary": "Ne olduğunu ve neden önemli olduğunu anlatan kısa özet (düzgün Türkçe, 1-2 cümle, max 200 karakter)",
    "trend_type": "viral",
    "source_url": "Gerçek kaynak URL (arama sonucundan, uydurma değil)"
  }
]
"""
    try:
        response_text = call_nim_with_search(prompt, max_tokens=900)

        import re
        match = re.search(r'\[\s*\{.*\}\s*\]', response_text, re.DOTALL)
        if match:
            clean_json = match.group(0).strip()
        else:
            clean_json = response_text.strip()
            if clean_json.startswith("```"):
                clean_json = clean_json.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        items = json.loads(clean_json)
        if isinstance(items, list) and len(items) > 0:
            count = 0
            # Diger icerik uretim script'lerimizle ayni yabanci-kelime-sizintisi kontrolu
            suspicious_words = ["thus", "however", "mejores", " and ", "para ", "with ",
                                 "release", "update", "launch", "feature", "first "]
            for item in items[:4]:
                title = item.get("title", "").strip()
                summary = item.get("summary", "").strip()
                url = item.get("source_url", "").strip()
                t_type = item.get("trend_type", "viral").strip()
                combined = f"{title} {summary}".lower()
                if any(w in combined for w in suspicious_words):
                    print(f"[NIM Trend Radar] Atlandi (yabanci kelime sizintisi supheli): {title}")
                    continue
                if not (title and summary):
                    continue
                # Kendi katalogumuzda eslesen bir urun yoksa bu trend'i kaydetme -
                # her gosterilen trend kendi inceleme sayfamiza yonlenmeli, dis linke degil.
                internal_slug = find_internal_slug_for_trend(title, summary)
                if not internal_slug:
                    print(f"[NIM Trend Radar] Atlandi (katalogumuzda eslesen urun yok): {title}")
                    continue
                save_ai_trend(title, summary, t_type, url, internal_slug=internal_slug)
                count += 1
            print(f"[NIM Trend Radar] {count} yeni trend gelisme kaydedildi!")
            return count > 0
        else:
            print("[NIM Trend Radar] Uyari: Yanit beklenen JSON dizisi formatinda gelmedi.")
    except Exception as e:
        print(f"[NIM Trend Radar] Hata olustu: {e}")
        # NIM/arama basarisiz olursa: kendi sistemimizden bahseden bir mesaj yerine,
        # hicbir sey eklemiyoruz - mevcut (varsa) eski trendler ekranda kalmaya devam eder,
        # yanlis/anlamsiz bir "trend" gostermek gostermemekten daha kotu.
        print("[NIM Trend Radar] Yeni trend eklenmedi, mevcut kayitlar korunuyor.")
    return False


if __name__ == "__main__":
    fetch_latest_ai_trends()
