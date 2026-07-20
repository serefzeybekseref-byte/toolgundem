# -*- coding: utf-8 -*-
"""
Otomatik uretilen icerigin (karsilastirma/koleksiyon) canliya cikmadan once
gectigi kalite kapisi. Tum otomatik icerik uretim scriptleri (auto_generate_comparisons.py,
generate_collections.py, ileride eklenecekler) bu modulden gecer.

3 seviye kontrol:
  1) Teknik   - yapi bozuk mu (bos alan, puan araligi disi, tekrar eden urun)
  2) Icerik   - cok kisa/generic/tekrarlayan metinler
  3) Mantik   - AI ciktisi, veritabanindaki objektif alanlarla (pricing_type, is_broken) celisiyor mu,
                veya eski/yanlis bir yil halusinasyonu iceriyor mu (ornek: "...2024" - site 2026'da)

Bilincli sadelestirme: ChatGPT'nin onerdigi 4 ayri alt-puan (Technical/Content/Logic/SEO)
+ 4 kademeli yayin esigi (95/90/80) bu olcekte (haftada ~5-8 yeni oge) gereksiz karmasiklik.
Onun yerine tek gecti/kaldi kapisi kullaniliyor: gecerse yayinlanir, kalirsa hic yazilmaz
ve sebepleri workflow'da GitHub Issue olarak raporlanir.
"""
import re
from datetime import datetime

GENERIC_PROS = {"iyi", "güzel", "kaliteli", "kullanışlı", "harika", "faydalı", "pratik"}


def _check_stale_year(text: str, label: str) -> list:
    """
    Baslik/intro icinde gecen 20XX yillarindan, mevcut yildan farkli olanlari yakalar.
    Ornek: site 2026'da calisirken baslikta "...2024" gormek AI halusinasyonuna/
    eski egitim verisine isaret eder - kullanicinin gordugu ilk seyin "eski/bayat"
    hissi vermesine yol acar.
    """
    problems = []
    current_year = datetime.utcnow().year
    for match in re.findall(r"\b(20\d{2})\b", text or ""):
        year = int(match)
        if year != current_year:
            problems.append(f"{label}: '{year}' yili geciyor ama gercek yil {current_year} - AI halusinasyonu olabilir")
    return problems


def _check_item_common(item, label):
    problems = []
    name = (item.get("name") or "").strip()
    if not name:
        problems.append(f"{label}: urun adi bos")
        name = "?"

    score = item.get("score")
    try:
        score = float(score)
        if not (1 <= score <= 10):
            problems.append(f"'{name}': puan 1-10 araliginin disinda ({score})")
    except (TypeError, ValueError):
        problems.append(f"'{name}': puan sayisal degil ({score!r})")

    pros = item.get("pros") or []
    cons = item.get("cons") or []
    if len(pros) < 2:
        problems.append(f"'{name}': en az 2 artı gerekli ({len(pros)} var)")
    if len(cons) < 1:
        problems.append(f"'{name}': en az 1 eksi gerekli")
    for p in pros:
        if p.strip().lower() in GENERIC_PROS:
            problems.append(f"'{name}': pros icinde cok genel/anlamsiz ifade: '{p}'")

    return problems, name, score


def check_comparison(title: str, intro: str, items: list, source_products_by_name: dict = None):
    """
    source_products_by_name: {name.lower(): product_dict} - gercek DB kayitlariyla
    capraz dogrulama icin (pricing_type, is_broken vb.)
    Donen: (ok: bool, problems: list[str])
    """
    problems = []

    if len(items) < 3:
        problems.append(f"en az 3 urun gerekli, {len(items)} var")

    names_seen = [(it.get("name") or "").strip().lower() for it in items]
    if len(names_seen) != len(set(names_seen)):
        problems.append("ayni urun birden fazla kez listede")

    if not title or len(title.strip()) < 10:
        problems.append("baslik cok kisa/bos")
    if not intro or len(intro.strip()) < 60:
        problems.append("intro 60 karakterden kisa")
    problems.extend(_check_stale_year(title, "baslik"))
    problems.extend(_check_stale_year(intro, "intro"))

    scores = []
    for it in items:
        item_problems, name, score = _check_item_common(it, "karsilastirma ogesi")
        problems.extend(item_problems)
        if isinstance(score, (int, float)):
            scores.append(score)

    if len(scores) >= 2 and len(set(scores)) == 1:
        problems.append("tum puanlar birebir ayni - AI urunleri ayirt etmemis olabilir")

    best_for_texts = [(it.get("best_for") or "").strip().lower() for it in items if it.get("best_for")]
    if len(best_for_texts) >= 2 and len(set(best_for_texts)) == 1:
        problems.append("'best_for' metni tum urunlerde birebir ayni")

    # Seviye 3: DB'deki objektif alanlarla mantik kontrolu
    if source_products_by_name:
        for it in items:
            name = (it.get("name") or "").strip()
            src = source_products_by_name.get(name.lower())
            if not src:
                continue
            pricing_text = (it.get("pricing") or "").lower()
            real_pricing = (src.get("pricing_type") or "").lower()
            if real_pricing == "ücretsiz" and "ücretli" in pricing_text and "ücretsiz" not in pricing_text:
                problems.append(f"'{name}': DB'de Ücretsiz ama AI metninde 'Ücretli' yaziyor")
            if real_pricing == "ücretli" and "ücretsiz" in pricing_text and "freemium" not in pricing_text:
                problems.append(f"'{name}': DB'de Ücretli ama AI metninde 'Ücretsiz' yaziyor")
            if src.get("is_broken"):
                full_text = f"{pricing_text} {(it.get('best_for') or '').lower()}"
                if "aktif" in full_text or "çalışıyor" in full_text:
                    problems.append(f"'{name}': site kirik (is_broken=true) ama AI aktifmis gibi bahsetmis")

    return (len(problems) == 0, problems)


def check_collection(title: str, description: str, items: list, source_products_by_id: dict = None):
    """
    source_products_by_id: {product_id: product_dict}
    Donen: (ok: bool, problems: list[str])
    """
    problems = []

    if len(items) < 4:
        problems.append(f"en az 4 urun gerekli, {len(items)} var")

    ids_seen = [it.get("product_id") for it in items]
    if len(ids_seen) != len(set(ids_seen)):
        problems.append("ayni urun birden fazla kez listede")

    if not title or len(title.strip()) < 8:
        problems.append("baslik cok kisa/bos")
    if not description or len(description.strip()) < 30:
        problems.append("description 30 karakterden kisa")

    reasons = [(it.get("reason") or "").strip().lower() for it in items if it.get("reason")]
    if len(reasons) >= 2 and len(set(reasons)) == 1:
        problems.append("'reason' metni tum urunlerde birebir ayni")
    for it in items:
        reason = (it.get("reason") or "").strip()
        if reason and len(reason) < 10:
            problems.append(f"product_id={it.get('product_id')}: reason cok kisa/anlamsiz ('{reason}')")

    if source_products_by_id:
        for it in items:
            pid = it.get("product_id")
            src = source_products_by_id.get(pid)
            if src is None:
                problems.append(f"product_id={pid}: bu ID veritabaninda yok (AI uydurmus olabilir)")

    return (len(problems) == 0, problems)


def check_guide(title: str, meta_description: str, content_html: str, word_count: int,
                 related_tool_slugs: list, source_tool_names: list = None):
    """
    Otomatik uretilen rehberler (generate_guide.py) icin kalite kapisi.
    source_tool_names: bu rehberin bahsetmesi GEREKEN arac isimleri (karsilastirmadan gelen liste) -
    verilirse, uretilen HTML icinde bu isimlerin gecip gecmedigi kontrol edilir (AI'nin
    aracin adini degistirip degistirmedigini/atlamadigini yakalamak icin).
    Donen: (ok: bool, problems: list[str])
    """
    problems = []

    if not title or len(title.strip()) < 10:
        problems.append("baslik cok kisa/bos")
    if not meta_description or len(meta_description.strip()) < 50:
        problems.append("meta_description 50 karakterden kisa (SEO icin zayif)")
    if not content_html or len(content_html.strip()) < 200:
        problems.append("content_html neredeyse bos")

    if word_count < 300:
        problems.append(f"kelime sayisi cok dusuk ({word_count}) - ic icerik olarak zayif kalir")

    if not related_tool_slugs or len(related_tool_slugs) < 3:
        problems.append(f"en az 3 eslesmis arac (internal_slug) gerekli, {len(related_tool_slugs or [])} var - "
                         f"eslesme bulunamayan araclar rehberde ic link/kart alamaz")

    problems.extend(_check_stale_year(title, "baslik"))

    if source_tool_names:
        content_lower = content_html.lower()
        missing = [name for name in source_tool_names if name.lower() not in content_lower]
        if missing:
            problems.append(f"su araclardan rehberde hic bahsedilmemis: {', '.join(missing)} (AI atlamis olabilir)")

    # Ayni cumlenin birebir tekrar etmesi (SSS/hatalar bolumlerinde AI'nin kendini tekrar etmesi)
    import re as _re
    sentences = [s.strip().lower() for s in _re.split(r"[.!?]\s+", content_html) if len(s.strip()) > 25]
    if sentences and len(sentences) != len(set(sentences)):
        dupes = len(sentences) - len(set(sentences))
        if dupes >= 2:
            problems.append(f"icerikte {dupes} adet birebir tekrar eden cumle var (AI kendini tekrarlamis olabilir)")

    return (len(problems) == 0, problems)
