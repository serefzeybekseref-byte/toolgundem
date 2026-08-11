# -*- coding: utf-8 -*-
"""
NVIDIA NIM (LLM) + Web Search (DuckDuckGo/ddgs) kullanarak her gün canlı AI haberlerini,
trendlerini ve sosyal medyada viral olan araçları tarar, ozetler ve ai_trends tablosuna yazar.
"""
import os
import json
import re
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from nim_tools import call_nim_with_search
from generate_content import call_gemini_grounded
from db import init_db, get_latest_ai_trends, find_internal_slug_for_trend, upsert_ai_trend_for_slug, prune_old_ai_trends


def _extract_json_array(text: str):
    """NIM/Gemini'den gelen (bazen fazladan aciklama iceren) metinden JSON dizisini
    ayiklar. Gemini'nin grounded modu JSON zorlamasini desteklemedigi icin (bkz.
    call_gemini_grounded docstring), her iki saglayici icin de bu esnek ayiklama
    kullaniliyor."""
    match = re.search(r'\[\s*\{.*\}\s*\]', text, re.DOTALL)
    if match:
        clean_json = match.group(0).strip()
    else:
        clean_json = text.strip()
        if clean_json.startswith("```"):
            clean_json = clean_json.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return json.loads(clean_json)


def fetch_latest_ai_trends():
    init_db()
    print("[NIM Trend Radar] Canli web aramasiyla gunun AI trendleri taraniyor...")

    prompt = """
Web araması (web_search) aracını kullanarak, gerçek/doğrulanabilir bir AI aracının son
birkaç gündeki somut bir güncelleme, yeni özellik veya gelişme haberini bul. 3 FARKLI
araç için ayrı ayrı ara.

ÖNEMLİ - ÇEŞİTLİLİK KURALI: Aracı sınırlı bir listeyle kısıtlama. Kataloğumuzda 1000'den
fazla AI aracı var (ChatGPT, Claude, Gemini, Midjourney, Canva, Notion, Perplexity,
ElevenLabs, Runway, Grammarly gibi çok bilinenlerin YANI SIRA; Cursor, Zapier, HubSpot,
Suno, Ideogram, Krea, Descript, Otter.ai, Jasper, Copy.ai gibi orta ölçekli/niş ama gerçek
ve tanınan araçlar da dahil). HER ÇALIŞTIRMADA aynı 2-3 en bilinen aracı (özellikle
ChatGPT ve Grammarly) tekrar tekrar seçme — farklı kategorilerden (görsel, video, kod,
otomasyon, yazı, ses vb.) farklı araçlar aramaya çalış.

DİĞER KURALLAR:
- "AI Araçları 2026" gibi genel/soyut başlık UYDURMA — her başlıkta MUTLAKA gerçek bir
  araç ismi geçmeli.
- Gerçekten yeni kurulmuş, henüz kimsenin duymadığı çok küçük/bilinmeyen lansmanlar değil;
  makul ölçüde tanınan, gerçek bir kullanıcı kitlesi olan araçlar tercih edilir.
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
    provider_used = "NIM"
    try:
        response_text = call_nim_with_search(prompt, max_tokens=900)
        items = _extract_json_array(response_text)
    except Exception as nim_err:
        print(f"[NIM Trend Radar] NIM basarisiz oldu ({nim_err}), Gemini (grounded web arama) ile tekrar deneniyor...")
        try:
            provider_used = "Gemini"
            response_text = call_gemini_grounded(prompt, max_tokens=900)
            items = _extract_json_array(response_text)
        except Exception as gemini_err:
            print(f"[NIM Trend Radar] Gemini de basarisiz oldu: {gemini_err}")
            print("[NIM Trend Radar] Yeni trend eklenmedi, mevcut kayitlar korunuyor.")
            return False

    try:
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
                # Ayni sirket/urun icin ESKI kayit varsa uzerine yazilir (upsert) -
                # boylece hicbir zaman ayni urunun 2 farkli tarihli kaydi birikmez,
                # her zaman sadece EN GUNCEL guncelleme gorunur.
                upsert_ai_trend_for_slug(title, summary, t_type, url, internal_slug)
                count += 1
            prune_old_ai_trends(keep_latest=20)
            print(f"[NIM Trend Radar] ({provider_used}) {count} yeni trend gelisme kaydedildi!")
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
