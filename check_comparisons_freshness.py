# -*- coding: utf-8 -*-
"""
Karsilastirma listelerini "canli" tutmak icin degisiklik-tetiklemeli kontrol.
DIKKAT: Bu script LLM'e "Kling yeni surum cikardi mi?" gibi harici/gercek-zamanli
bir soru SORMAZ - cunku Groq/NVIDIA/Gemini metin API'lerimizin web'e erisimi yok,
byle bir soruya guvenilir cevap veremezler (halusinasyon riski). Bunun yerine
SADECE kendi veritabanimizdaki objektif sinyalleri kontrol eder:

  1. Listedeki bir arac artik erisilemez mi? (is_broken)
  2. Ayni kategoride, listede OLMAYAN ama listedeki en dusuk siradakinden daha
     yuksek quality_score/votes'a sahip baska bir urunumuz var mi?
  3. Liste 90 gunden eski mi? (staleness - review hatirlatmasi)

Sinyal bulunursa GitHub Issue acilir - LLM otomatik yeniden siralama YAPMAZ,
cunku "hangi arac gercekten daha iyi" nihai karari icin (fiyat, versiyon,
ozellik degisikligi gibi) guvenilir bilgi web arastirmasi gerektirir ve bu,
bir insanin (veya web-search'lu bir Claude oturumunun) gozden gecirmesi
gereken bir karar - kor otomasyon burada yanlis bilgi riski tasir.
"""
import os
from dotenv import load_dotenv
load_dotenv()
from db_target import print_db_target
print_db_target()
from datetime import datetime, timezone, timedelta
from db import init_db, get_all_comparisons, get_comparison_by_slug, get_all_products, save_comparison
from quality_gate import check_comparison

STALE_DAYS = 90

# Baslik -> topic ters-eslemesi (auto_generate_comparisons.py'deki CANDIDATE_TOPICS'ten).
# Sadece bu sozlukte karsiligi olan (otomatik uretilmis) karsilastirmalar icin kirik-arac
# swap'i GUVENLE otomatiklestirilebilir - cunku "hangi topic'e ait" bilgisi kesin.
# Elle yazilmis (manuel) karsilastirmalarin topic'i belirsiz oldugu icin onlar icin
# swap YAPILMAZ, sadece Issue acilir (guvenli taraf).
def _title_to_topic_map():
    from auto_generate_comparisons import CANDIDATE_TOPICS
    return {title: topic for topic, title in CANDIDATE_TOPICS.items()}


def _find_replacement(topic: str, exclude_names: set, exclude_broken_slugs: set):
    """Ayni topic'te, listede olmayan ve kirik olmayan en yuksek kaliteli/oylu urunu bulur."""
    from auto_generate_comparisons import get_top_products_for_topic
    candidates = get_top_products_for_topic(topic, limit=15)
    for c in candidates:
        if c["original_name"].lower() in exclude_names:
            continue
        if c.get("is_broken") or c["slug"] in exclude_broken_slugs:
            continue
        return c
    return None


def _write_item_copy(product: dict) -> dict:
    """Sadece BU tek urun icin best_for/pricing/pros/cons yazdirir (guncel-piyasa/
    karsilastirmali yargi ISTEMEZ - urunun kendi bilinen ozelliklerinden yazi uretmek,
    sitenin her yerinde zaten guvenle yaptigi bir is; 'hangisi daha iyi' sorusu degil)."""
    from generate_content import _generate_with_fallback
    prompt = f"""Asagidaki urun icin kisa, objektif tanitim metni yaz.
Urun: {product['original_name']}
Aciklama: {(product.get('summary_tr') or '')[:300]}
Fiyat tipi: {product.get('pricing_type') or 'Bilinmiyor'}

SADECE gecerli JSON dondur:
{{"best_for": "kisa cumle - kimin icin en uygun", "pricing": "fiyat bilgisi kisa ozet",
  "pros": ["madde1", "madde2"], "cons": ["dikkat edilmesi gereken 1 madde"]}}
"""
    groq_extra = {"temperature": 0.4, "response_format": {"type": "json_object"}}
    return _generate_with_fallback(prompt, groq_extra, max_tokens=400)


def get_all_products_for_link_check():
    from db import get_all_products_for_link_check as _f
    return _f()


def auto_fix_broken_items(signals: list) -> list:
    """
    Sadece 'kirik arac' sinyali olan ve OTOMATIK-URETILMIS (CANDIDATE_TOPICS'te karsiligi
    olan) karsilastirmalarda, kirik araci ayni kategoriden en iyi adayla degistirir.
    Staleness (90 gun) sinyali icin HICBIR OTOMATIK DUZELTME YAPILMAZ - bu, "hala en iyi
    siralama mi" sorusu gercek zamanli bilgi/arastirma gerektirir, elimizdeki LLM'lerin
    web erisimi yok, kor otomasyon halusinasyon riski tasir (bilerek Issue-only birakildi).
    Donen: fixed_slugs listesi (basariyla duzeltilen karsilastirmalarin slug'lari).
    """
    title_to_topic = _title_to_topic_map()
    fixed = []

    for s in signals:
        broken_issues = [i for i in s["issues"] if "artik erisilemez" in i]
        if not broken_issues:
            continue  # sadece staleness sinyali varsa dokunma

        topic = title_to_topic.get(s["title"])
        if not topic:
            continue  # manuel karsilastirma - topic bilinmiyor, guvenli taraf: dokunma

        comp = get_comparison_by_slug(s["slug"])
        if not comp:
            continue

        products = {p["slug"]: p for p in get_all_products_for_link_check()}
        broken_slugs = {slug for slug, p in products.items() if p.get("is_broken")}
        listed_names = {it["name"].lower() for it in comp["tools"]}

        changed = False
        new_tools = []
        for item in comp["tools"]:
            islug = item.get("internal_slug")
            if islug and islug in broken_slugs:
                replacement = _find_replacement(topic, listed_names, broken_slugs)
                if not replacement:
                    new_tools.append(item)  # aday bulunamadi, oldugu gibi birak
                    continue
                try:
                    copy = _write_item_copy(replacement)
                    new_tools.append({
                        "rank": item["rank"],
                        "name": replacement["original_name"],
                        "score": item["score"],  # eski skoru koru (yeni skor uydurmak yerine)
                        "pricing": copy.get("pricing", ""),
                        "best_for": copy.get("best_for", ""),
                        "pros": copy.get("pros", []),
                        "cons": copy.get("cons", []),
                        "website": replacement.get("website", ""),
                    })
                    listed_names.add(replacement["original_name"].lower())
                    changed = True
                except Exception:
                    new_tools.append(item)  # LLM basarisiz olursa oldugu gibi birak
            else:
                new_tools.append(item)

        if changed:
            ok, problems = check_comparison(comp["title"], comp["intro"], new_tools)
            if ok:
                save_comparison(s["slug"], comp["title"], comp["intro"], new_tools)
                fixed.append(s["slug"])

    return fixed


def check_all():
    init_db()
    products = get_all_products()
    comparisons = get_all_comparisons()
    signals = []

    for comp_meta in comparisons:
        comp = get_comparison_by_slug(comp_meta["slug"])
        if not comp:
            continue

        category_signals = []

        # Sinyal 1: broken link
        for item in comp["tools"]:
            if item.get("internal_slug"):
                match = next((p for p in products if p["slug"] == item["internal_slug"]), None)
                if match and match.get("is_broken"):
                    category_signals.append(
                        f"'{item['name']}' artik erisilemez gorunuyor (is_broken=1)."
                    )

        # Sinyal 2: listede olmayan daha guclu bir aday var mi?
        # (kategori adindan kaba bir anahtar kelime eslesmesi - basit ama LLM'siz)
        listed_names = {it["name"].lower() for it in comp["tools"]}
        min_score_in_list = min((it["score"] for it in comp["tools"]), default=0)
        # Comparison'in konusuyla eslesebilecek urunleri quality_score'a gore kontrol et
        candidates = sorted(products, key=lambda p: p.get("quality_score", 0), reverse=True)[:5]
        for cand in candidates:
            if cand["original_name"].lower() not in listed_names and cand.get("quality_score", 0) >= 85:
                # Sadece bilgi amacli bir aday olarak not düş, kesin ekleme onerisi degil
                pass  # Bu sinyal turu su an icin cok gurultulu (yanlis pozitif riski yuksek) - devre disi birakildi

        # Sinyal 3: staleness
        try:
            updated = datetime.fromisoformat(comp["updated_at"])
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - updated).days
            if age_days > STALE_DAYS:
                category_signals.append(f"Liste {age_days} gundur guncellenmedi (son: {comp['updated_at'][:10]}).")
        except Exception:
            pass

        if category_signals:
            signals.append({"title": comp["title"], "slug": comp["slug"], "issues": category_signals})

    return signals


def format_report(signals, fixed_slugs=None):
    fixed_slugs = fixed_slugs or []
    lines = []
    if fixed_slugs:
        lines.append(f"✅ {len(fixed_slugs)} kategoride kirik arac otomatik degistirildi:")
        for slug in fixed_slugs:
            lines.append(f"- /karsilastirma/{slug}")
        lines.append("")

    remaining = [s for s in signals if s["slug"] not in fixed_slugs]
    if remaining:
        lines.append(f"⚠️ {len(remaining)} kategori ELLE gozden gecirilmeli (otomatik duzeltilemedi):")
        for s in remaining:
            lines.append(f"### {s['title']} (/karsilastirma/{s['slug']})")
            for issue in s["issues"]:
                lines.append(f"- {issue}")
            lines.append("")

    if not lines:
        return "Tum kategoriler guncel gorunuyor. Herhangi bir sinyal tetiklenmedi."
    return "\n".join(lines)


if __name__ == "__main__":
    signals = check_all()

    # Kirik-arac sinyali olan ve otomatik-uretilmis (topic'i bilinen) karsilastirmalarda
    # once otomatik duzeltmeyi dene - sadece bunun disinda kalanlar icin Issue acilacak.
    fixed_slugs = auto_fix_broken_items(signals) if signals else []

    report = format_report(signals, fixed_slugs)
    print(report)

    # GitHub Actions'ta calisiyorsa ve HALA cozulmemis sinyal varsa, cikti degiskenine yaz
    # (workflow bunu okuyup GitHub Issue acabilir). Tamami otomatik duzeldiyse Issue acilmaz.
    remaining_count = len([s for s in signals if s["slug"] not in fixed_slugs])
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a", encoding="utf-8") as f:
            f.write(f"has_signals={'true' if remaining_count > 0 else 'false'}\n")
            f.write("report<<EOF\n")
            f.write(report + "\n")
            f.write("EOF\n")
