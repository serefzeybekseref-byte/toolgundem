# -*- coding: utf-8 -*-
"""
Fiyat tazeleme: pricing_type'i "Bilinmiyor" olan urunler icin GERCEK web aramasi
(Gemini grounded search) ile fiyatlandirma tipini bulmaya calisir.

NOT: Mevcut backfill_quickfacts.py de pricing_type dolduruyor ama SADECE var olan
Turkce metinden LLM tahmini yapiyor (web erisimi yok) - metinde fiyat hic gecmiyorsa
"Bilinmiyor" olarak kalmaya mahkum. Bu script, o "cikmaz" durumdaki urunler icin
gercek web aramasiyla devreye giriyor - iki script CAKISMIYOR, tamamliyor.

GUVENLI YON: sadece "Bilinmiyor" -> bilinen bir deger yaziyor (bilinmezden bilinene
gitmek risksiz). Zaten bilinen bir pricing_type'i grounded arama sonucuna gore
DEGISTIRMEZ (o, check_comparisons_freshness.py'deki gibi Issue-only/insan-onayli
bir is olurdu, ayri bir gorev - simdilik kapsam disi).

Kullanim: python refresh_pricing.py [batch_size]
"""
import sys
import re
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

VALID_TYPES = {"Ücretsiz", "Freemium", "Ücretli"}


def _classify_from_grounded_note(note: str) -> str | None:
    """Gemini'nin grounded aramadan donen serbest metnini, kesin bir pricing_type'a
    cevirir. Metni bastan LLM'e JSON zorlatmiyoruz (grounded+json guvenilir calismiyor,
    bkz. generate_content.py notu) - bunun yerine anahtar kelime taramasi yapiyoruz."""
    if not note:
        return None
    lower = note.lower()
    # Once en spesifikten en genele dogru kontrol (freemium, "ucretsiz VE ucretli" iceriyorsa
    # once yakalanmali, yoksa yanlislikla "Ucretsiz" damgalanir).
    if any(k in lower for k in ["freemium", "ücretsiz katman", "ücretsiz plan", "hem ücretsiz hem"]):
        return "Freemium"
    if any(k in lower for k in ["tamamen ücretsiz", "tamamen bedava", "her zaman ücretsiz", "free forever"]):
        return "Ücretsiz"
    if any(k in lower for k in ["yalnızca ücretli", "sadece ücretli", "ücretsiz plan yok", "ücretsiz sürüm yok"]):
        return "Ücretli"
    if any(k in lower for k in ["ücretsiz"]) and any(k in lower for k in ["ücretli", "$/ay", "aylık ücret", "abonelik"]):
        return "Freemium"
    if "ücretsiz" in lower:
        return "Ücretsiz"
    if any(k in lower for k in ["ücretli", "$/ay", "abonelik", "aylık"]):
        return "Ücretli"
    return None


def refresh_batch(batch_size: int = 15):
    from db import get_connection
    from generate_content import call_gemini_grounded

    conn = get_connection()
    rows = conn.execute(
        "SELECT id, slug, original_name, website FROM products "
        "WHERE pricing_type = 'Bilinmiyor' OR pricing_type IS NULL "
        "ORDER BY quality_score DESC LIMIT ?",
        (batch_size,)
    ).fetchall()
    conn.close()

    if not rows:
        print("Fiyati bilinmeyen urun kalmadi.")
        return {"updated": 0, "checked": 0}

    ay_yil = datetime.now(timezone.utc).strftime("%B %Y")
    updated = 0
    details = []

    for idx, r in enumerate(rows):
        r = dict(r)
        if idx > 0:
            time.sleep(4)  # grounded arama kotasi siki - art arda isteklerde 429 riski var
        prompt = (
            f"Su an {ay_yil}. '{r['original_name']}' adli AI aracinin GUNCEL fiyatlandirma "
            f"modelini web'den kontrol et. Sadece su bilgiyi ver: tamamen ucretsiz mi, "
            f"ucretsiz+ucretli (freemium) katmani mi var, yoksa sadece ucretli mi? "
            f"2 cumleyi gecme, Turkce cevap ver. Emin degilsen 'bulamadim' de, uydurma."
        )
        try:
            note = call_gemini_grounded(prompt, max_tokens=150)
        except Exception as e:
            details.append(f"  {r['original_name']}: arama hatasi ({type(e).__name__})")
            continue

        classified = _classify_from_grounded_note(note)
        if not classified:
            details.append(f"  {r['original_name']}: siniflandirilamadi ('{note[:60]}...')")
            continue

        conn2 = get_connection()
        conn2.execute("UPDATE products SET pricing_type = ? WHERE id = ?", (classified, r["id"]))
        conn2.commit()
        conn2.close()
        updated += 1
        details.append(f"  {r['original_name']}: -> {classified}")

    print(f"Tamamlandi. {len(rows)} urun kontrol edildi, {updated} tanesi guncellendi.")
    for d in details:
        print(d)
    return {"updated": updated, "checked": len(rows)}


if __name__ == "__main__":
    batch = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    refresh_batch(batch)
