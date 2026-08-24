"""
PH (Product Hunt) jenerik "thumbnail saglanmadi" placeholder'ini kullanan
urunleri tespit edip temizler.

Yontem:
1. Onceden dogrulanmis placeholder dosyasinin (Typillar ornegi) SHA-256 hash'i
   referans alinir.
2. thumbnail alani ph-files.imgix.net'ten gelen TUM urunler taranir (HEAD
   istegiyle Content-Length kontrolu - hizli, indirme yok).
3. Content-Length kucuk (< 5000 byte) olanlar SADECE o zaman tam indirilip
   hash karsilastirilir.
4. Hash TAM ESLESIRSE -> thumbnail NULL yapilir (harf-avatari fallback devreye girer).
5. Kucuk ama hash farkli olanlar OTOMATIK DEGISTIRILMEZ - ayri bir rapora
   yazilir (manuel inceleme icin - yanlislikla mesru kucuk bir logoyu
   silmemek adina guvenli taraf).

Kullanim: python cleanup_ph_placeholder_thumbnails.py
"""
import hashlib
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

from app import app
from db import get_connection

REFERANS_URL = "https://ph-files.imgix.net/74ad3db6-a7bb-4dc9-b570-1c95489d50d5.png?auto=format"
BOYUT_ESIGI = 5000  # byte
MAKS_THREAD = 12

def referans_hash_al():
    r = requests.get(REFERANS_URL, timeout=15)
    r.raise_for_status()
    return hashlib.sha256(r.content).hexdigest()

def kontrol_et(row, referans_hash):
    pid, slug, url = row["id"], row["slug"], row["thumbnail"]
    try:
        head = requests.head(url, timeout=10, allow_redirects=True)
        boyut = int(head.headers.get("Content-Length", -1))
    except Exception as e:
        return ("hata", pid, slug, url, str(e))

    if boyut == -1 or boyut >= BOYUT_ESIGI:
        return ("temiz", pid, slug, url, boyut)

    # Kucuk dosya - tam indirip hash karsilastir
    try:
        full = requests.get(url, timeout=15)
        gercek_hash = hashlib.sha256(full.content).hexdigest()
    except Exception as e:
        return ("hata", pid, slug, url, str(e))

    if gercek_hash == referans_hash:
        return ("placeholder_eslesti", pid, slug, url, boyut)
    else:
        return ("kucuk_ama_farkli", pid, slug, url, boyut)

def main():
    print(">> Referans placeholder hash hesaplaniyor...")
    referans_hash = referans_hash_al()
    print(f">> Referans hash: {referans_hash[:16]}...")

    with app.app_context(), app.test_request_context():
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, slug, thumbnail FROM products WHERE thumbnail LIKE ?",
            ("%ph-files.imgix.net%",)
        ).fetchall()
        rows = [dict(r) for r in rows]
        print(f">> Taranacak urun sayisi: {len(rows)}")

        sonuclar = {"temiz": [], "placeholder_eslesti": [], "kucuk_ama_farkli": [], "hata": []}
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=MAKS_THREAD) as ex:
            futures = [ex.submit(kontrol_et, r, referans_hash) for r in rows]
            tamamlanan = 0
            for fut in as_completed(futures):
                sonuc = fut.result()
                sonuclar[sonuc[0]].append(sonuc)
                tamamlanan += 1
                if tamamlanan % 200 == 0:
                    print(f"   ... {tamamlanan}/{len(rows)} kontrol edildi ({time.time()-t0:.0f}s)")

        print(f">> Tarama tamamlandi ({time.time()-t0:.0f}s)")
        print(f"   Temiz: {len(sonuclar['temiz'])}")
        print(f"   Placeholder eslesti (DUZELTILECEK): {len(sonuclar['placeholder_eslesti'])}")
        print(f"   Kucuk ama hash farkli (MANUEL INCELE): {len(sonuclar['kucuk_ama_farkli'])}")
        print(f"   Hata: {len(sonuclar['hata'])}")

        # Eslesenleri DB'de NULL'a cek
        for _, pid, slug, url, boyut in sonuclar["placeholder_eslesti"]:
            conn.execute("UPDATE products SET thumbnail = NULL WHERE id = ?", (pid,))
        conn.commit()
        print(f">> {len(sonuclar['placeholder_eslesti'])} urunun thumbnail'i NULL yapildi (artik harf-avatari gosterilecek).")

        # Rapor dosyasi yaz
        with open("_ph_placeholder_report.txt", "w", encoding="utf-8") as f:
            f.write("=== DUZELTILEN (placeholder eslesti) ===\n")
            for _, pid, slug, url, boyut in sonuclar["placeholder_eslesti"]:
                f.write(f"{slug}\t{url}\n")
            f.write("\n=== MANUEL INCELE (kucuk ama hash farkli) ===\n")
            for _, pid, slug, url, boyut in sonuclar["kucuk_ama_farkli"]:
                f.write(f"{slug}\t{boyut}byte\t{url}\n")
            f.write("\n=== HATA (kontrol edilemedi) ===\n")
            for _, pid, slug, url, err in sonuclar["hata"]:
                f.write(f"{slug}\t{err}\t{url}\n")
        print(">> Rapor: _ph_placeholder_report.txt")

if __name__ == "__main__":
    main()
