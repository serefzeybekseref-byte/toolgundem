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
Web aramasi (web_search) aracini kullanarak, TANINMIS/POPULER bir AI aracinin (ChatGPT,
Claude, Gemini, Midjourney, Canva, Notion, Perplexity, ElevenLabs, Runway, Grammarly gibi
cok bilinen, yaygin kullanilan araclardan biri - kucuk/bilinmeyen yeni lansmanlar DEGIL)
son birkac gundeki somut bir guncelleme/ozellik haberini bul. 3 farkli TANINMIS arac icin
ayri ayri ara.

ONEMLI: "AI Araclari 2026" gibi genel/soyut baslik UYDURMA - her baslikta MUTLAKA
yukaridaki gibi TANINMIS, gercek bir arac ismi gecmeli.

Bize TAM OLARAK asagidaki JSON formatinda bir yanit ver. Baska hicbir giris veya aciklama yazma, SADECE gecerli bir JSON array dondur:

[
  {
    "title": "Taninmis arac ismi gecen, spesifik gelisme basligi (Turkce, max 60 karakter)",
    "summary": "Ne oldugunu ve neden onemli oldugunu anlatan kisa ozet (Turkce, 1-2 cumle, max 200 karakter)",
    "trend_type": "viral",
    "source_url": "Gercek kaynak URL (arama sonucundan, uydurma degil)"
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
