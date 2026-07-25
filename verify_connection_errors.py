# -*- coding: utf-8 -*-
"""
"connection_error" ile isaretli kirik urunleri NIM+web aramasiyla ikinci kez dogrular.

Neden sadece 'connection_error' ve '404' degil:
- connection_error: bizim sunucumuz siteye hic ulasamadi (firewall/bot-engelleme/gecici
  ag sorunu olabilir, sitenin gercekten olup olmadigiyla ilgisi olmayabilir) - BELIRSIZ sinyal.
- 404: site cevap verdi ama sayfa yok - DAHA GUVENILIR bir "gercekten kirik" sinyali,
  bu yuzden bu script'in kapsamina almiyoruz (yanlislikla canli bir urunu "aktif" diye
  isaretleyip kullanicini yanlis yonlendirme riskini almiyoruz).

Guvenlik: Sadece web aramasindan GUCLU/NET bir "hala aktif" sinyali gelirse otomatik
duzeltiyoruz (is_broken=0). Belirsiz durumlarda dokunmuyoruz - varsayilan hep "kirik
kalsin" (kullaniciya yanlis/olu link gostermekten daha guvenli, cunku o taraf zaten
keşif yuzeylerinden gizli).
"""
import re
from dotenv import load_dotenv
load_dotenv()

from db import get_connection, init_db
from nim_tools import call_nim_with_search

VERIFY_PROMPT = """"{name}" adinda bir yazilim/AI araci var. Web sitesi: {website}

web_search aracini kullanarak bu urunun 2026 yilinda hala aktif, calisan bir urun/servis
olup olmadigini arastir. Arastirma sonucuna dayanarak SADECE su formatta cevap ver:

DURUM: AKTIF veya DURUM: KAPALI veya DURUM: BELIRSIZ
SEBEP: (tek cumle, aramada bulduguna dayanarak)
"""


def verify_one(name: str, website: str) -> dict:
    prompt = VERIFY_PROMPT.format(name=name, website=website)
    response = call_nim_with_search(prompt, max_tokens=200)
    match = re.search(r"DURUM:\s*(AKTIF|KAPALI|BEL[İI]RS[İI]Z)", response, re.IGNORECASE)
    status = match.group(1).upper() if match else "BELIRSIZ"
    reason_match = re.search(r"SEBEP:\s*(.+)", response)
    reason = reason_match.group(1).strip() if reason_match else response[:200]
    return {"status": status, "reason": reason, "raw": response}


def run():
    init_db()
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, original_name, website FROM products WHERE is_broken = 1 AND broken_reason = 'connection_error'"
    ).fetchall()
    conn.close()

    print(f"{len(rows)} 'connection_error' urunu dogrulanacak.\n")
    fixed, kept_broken, unclear = 0, 0, 0

    for r in rows:
        d = dict(r)
        print(f"[{d['original_name']}] ({d['website']})")
        try:
            result = verify_one(d["original_name"], d["website"])
        except Exception as e:
            print(f"  (ilk deneme basarisiz: {e}, tekrar deneniyor...)")
            try:
                result = verify_one(d["original_name"], d["website"])
            except Exception as e2:
                print(f"  HATA: {e2}")
                unclear += 1
                continue
        print(f"  -> {result['status']}: {result['reason']}")

        if "AKTIF" in result["status"]:
            conn = get_connection()
            conn.execute(
                "UPDATE products SET is_broken = 0, broken_reason = NULL WHERE id = ?",
                (d["id"],)
            )
            conn.commit()
            conn.close()
            print(f"  -> DUZELTILDI: artik kirik degil olarak isaretlendi.")
            fixed += 1
        elif "KAPALI" in result["status"]:
            kept_broken += 1
        else:
            unclear += 1

    print(f"\nSonuc: {fixed} urun duzeltildi, {kept_broken} gercekten kapali dogrulandi, {unclear} belirsiz/hata.")


if __name__ == "__main__":
    run()
