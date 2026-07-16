"""
Ana pipeline: Product Hunt'tan urunleri ceker, yeni olanlar icin
Turkce icerik uretir ve veritabanina kaydeder.
Bu script GitHub Actions ile zamanlanip calistirilacak (ASAMA 7).
"""
import time
from fetch_producthunt import get_latest_products
from generate_content import generate_turkish_content
from db import init_db, product_exists, save_product, find_possible_duplicate


def run():
    init_db()
    products = get_latest_products()
    print(f"Product Hunt'tan {len(products)} urun cekildi.")

    new_count = 0
    for product in products:
        if product_exists(product["id"]):
            print(f"  [atlandi] {product['name']} (zaten var - ayni ph_id)")
            continue

        dup = find_possible_duplicate(product["name"], product.get("website", ""))
        if dup:
            print(f"  [atlandi] {product['name']} (muhtemel duplicate: '{dup['original_name']}' zaten var)")
            continue

        print(f"  [yeni] {product['name']} icin Turkce icerik uretiliyor...")
        try:
            ai_content = generate_turkish_content(product)
            slug = save_product(product, ai_content)
            print(f"    -> kaydedildi: /urun/{slug}")
            new_count += 1
            time.sleep(1)  # Groq rate limitine takilmamak icin kucuk bir bekleme
        except Exception as e:
            print(f"    !! HATA: {product['name']} icin icerik uretilemedi: {e}")

    print(f"\nTamamlandi. {new_count} yeni urun eklendi.")


if __name__ == "__main__":
    run()
