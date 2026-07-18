# -*- coding: utf-8 -*-
"""
Ana pipeline: Product Hunt'tan urunleri ceker, yeni olanlar icin
Turkce icerik uretir ve veritabanina kaydeder.
Bu script GitHub Actions ile zamanlanip calistirilacak (ASAMA 7).
"""
import os
import time
from fetch_producthunt import get_latest_products
from generate_content import generate_turkish_content
from check_links import check_url
from db import (
    init_db, product_exists, save_product, find_possible_duplicate,
    log_pipeline_run, should_alert_zero_new, mark_link_checked, get_product_by_slug,
)


def run():
    init_db()
    products = get_latest_products()
    print(f"Product Hunt'tan {len(products)} urun cekildi.")

    new_count = 0
    error_count = 0
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

            # Yeni eklenen urunun linkini hemen kontrol et (haftalik taramayi beklemeden)
            try:
                saved = get_product_by_slug(slug)
                website = saved.get("website") or saved.get("ph_url")
                is_up = check_url(website)
                mark_link_checked(saved["id"], is_broken=not is_up)
                if not is_up:
                    print(f"    !! UYARI: {product['name']} linki kirik/erisilemiyor -> {website}")
            except Exception as link_err:
                print(f"    (link kontrolu atlandi: {link_err})")

            time.sleep(1)  # Groq rate limitine takilmamak icin kucuk bir bekleme
        except Exception as e:
            print(f"    !! HATA: {product['name']} icin icerik uretilemedi: {e}")
            error_count += 1

    print(f"\nTamamlandi. {new_count} yeni urun eklendi, {error_count} hata.")

    log_pipeline_run(new_count, error_count)
    alert = should_alert_zero_new()
    if alert:
        print("UYARI: Son 2+ gundur hic yeni urun eklenmiyor - Product Hunt API'sinde bir sorun olabilir.")

    # GitHub Actions'ta calisiyorsa, sonraki adimin (issue acma) okuyabilmesi icin ciktiyi yaz
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a", encoding="utf-8") as f:
            f.write(f"new_count={new_count}\n")
            f.write(f"error_count={error_count}\n")
            f.write(f"zero_new_alert={'true' if alert else 'false'}\n")


if __name__ == "__main__":
    run()
