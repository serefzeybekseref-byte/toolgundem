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
from db import init_db, save_ai_trend, get_latest_ai_trends


def fetch_latest_ai_trends():
    init_db()
    print("[NIM Trend Radar] Canli web aramasiyla gunun AI trendleri taraniyor...")

    prompt = """
Lutfen web aramasi (web_search) aracini kullanarak son 48 saat icinde AI (Yapay Zeka) dunyasinda yaşanan en onemli 3 viral gelismeyi veya trend AI aracini ara ve bul.

Arama sorgun: "latest trending AI tools news viral AI update 2026"

Bize TAM OLARAK asagidaki JSON formatinda bir yanit ver. Baska hicbir giris veya aciklama yazma, SADECE gecerli bir JSON array dondur:

[
  {
    "title": "Gelisme veya Arac Basligi (Turkce, vurucu, max 60 karakter)",
    "summary": "Ne hakkinda oldugunu ve neden onemli oldugunu anlatan kisa ozet (Turkce, 1-2 cumle, max 200 karakter)",
    "trend_type": "viral",
    "source_url": "Varsa kaynak URL veya bos metin"
  }
]
"""
    try:
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
            for item in items[:4]:
                title = item.get("title", "").strip()
                summary = item.get("summary", "").strip()
                url = item.get("source_url", "").strip()
                t_type = item.get("trend_type", "viral").strip()
                if title and summary:
                    save_ai_trend(title, summary, t_type, url)
                    count += 1
            print(f"[NIM Trend Radar] {count} yeni trend gelisme kaydedildi!")
            return True
        else:
            print("[NIM Trend Radar] Uyari: Yanit beklenen JSON dizisi formatinda gelmedi.")
    except Exception as e:
        print(f"[NIM Trend Radar] Hata olustu: {e}")
        # Fallback default item if NIM quota/network issue
        existing = get_latest_ai_trends(1)
        if not existing:
            save_ai_trend(
                "NVIDIA NIM & Llama 3.3 Entegrasyonu Aktifleşti",
                "BulurumAI, en güncel yapay zeka araçlarını canlı web aramasıyla otomatik olarak tarayıp doğrulamaya başladı.",
                "update",
                "https://bulurumai.com"
            )
    return False


if __name__ == "__main__":
    fetch_latest_ai_trends()
