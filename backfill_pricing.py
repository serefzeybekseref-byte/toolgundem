# -*- coding: utf-8 -*-
"""
'pricing_type = Bilinmiyor' olarak takili kalmis urunler icin SADECE fiyat
siniflandirmasini yeniden dener (why_use_it/key_features/platforms'a dokunmaz).
Bkz. db.py get_products_with_unknown_pricing() - 23 Temmuz 2026'da bulunan,
get_products_missing_quickfacts()'in yakalayamadigi bir backfill boslugu.

Kullanim: python backfill_pricing.py [adet]  (varsayilan: 30)
"""
import sys
import io
# Bazi urun adlari nadir Unicode karakterler icerebiliyor (Vietnamca vb.) -
# Windows konsolunun varsayilan cp1254 kodlamasi bunlari yazdiramayip script'i
# yariyolda cokertiyordu (46/100 urunde oldu). UTF-8'e zorluyoruz.
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import time
import json
from dotenv import load_dotenv
load_dotenv()
from db import init_db, get_products_with_unknown_pricing, update_product_pricing_type
from generate_content import _generate_with_fallback

PROMPT_TMPL = """Asagidaki yapay zeka/teknoloji urunu icin fiyatlandirma modelini belirle.

Urun adi: {name}
Aciklama: {summary}
Etiketler: {tags}
Website: {website}

Sadece elindeki bilgiden makul bir CIKARIM yap - website'e gidip bakamiyorsun, uydurma
yapma, gercekten belirsizse "Bilinmiyor" yaz (bu da gecerli bir cevap).

Secenekler (TAM OLARAK birini yaz):
- "Ucretsiz" (tamamen bedava, ucretli plani yok)
- "Freemium" (ucretsiz katman + ucretli ust plan var)
- "Ucretli" (sadece ucretli, deneme suresi olabilir ama surekli kullanim ucretli)
- "Bilinmiyor" (elindeki bilgiyle karar veremiyorsan)

SADECE gecerli JSON dondur, baska hicbir metin ekleme:
{{"pricing_type": "..."}}
"""


def run(batch_size=30):
    init_db()
    products = get_products_with_unknown_pricing(limit=batch_size)
    if not products:
        print("Fiyati bilinmeyen urun kalmadi.")
        return 0, 0

    resolved, still_unknown = 0, 0
    for p in products:
        prompt = PROMPT_TMPL.format(
            name=p["original_name"],
            summary=(p.get("summary_tr") or "")[:300],
            tags=p.get("tags") or "",
            website=p.get("website") or "",
        )
        try:
            groq_extra = {"temperature": 0.3, "response_format": {"type": "json_object"}}
            result = _generate_with_fallback(prompt, groq_extra, max_tokens=100)
            pricing_type = (result.get("pricing_type") or "Bilinmiyor").strip()
            if pricing_type not in ("Ücretsiz", "Freemium", "Ücretli", "Bilinmiyor"):
                pricing_type = "Bilinmiyor"  # LLM beklenmedik bir sey yazdiysa guvenli tarafta kal
            update_product_pricing_type(p["id"], pricing_type)
            if pricing_type == "Bilinmiyor":
                still_unknown += 1
                print(f"  [hala bilinmiyor] {p['original_name']}")
            else:
                resolved += 1
                print(f"  [cozuldu] {p['original_name']} -> {pricing_type}")
        except Exception as e:
            print(f"  !! HATA: {p['original_name']}: {e}")
        time.sleep(1)

    print(f"\nBitti. Cozulen: {resolved}, hala bilinmiyor (gercekten belirsiz): {still_unknown}")
    return resolved, still_unknown


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    run(batch_size=n)
