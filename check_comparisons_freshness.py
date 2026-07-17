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
from datetime import datetime, timezone, timedelta
from db import init_db, get_all_comparisons, get_comparison_by_slug, get_all_products

STALE_DAYS = 90


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


def format_report(signals):
    if not signals:
        return "Tum kategoriler guncel gorunuyor. Herhangi bir sinyal tetiklenmedi."
    lines = [f"{len(signals)} kategori gozden gecirilmeli:\n"]
    for s in signals:
        lines.append(f"### {s['title']} (/karsilastirma/{s['slug']})")
        for issue in s["issues"]:
            lines.append(f"- {issue}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    signals = check_all()
    report = format_report(signals)
    print(report)

    # GitHub Actions'ta calisiyorsa ve sinyal varsa, cikti degiskenine yaz
    # (workflow bunu okuyup GitHub Issue acabilir).
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a", encoding="utf-8") as f:
            f.write(f"has_signals={'true' if signals else 'false'}\n")
            f.write("report<<EOF\n")
            f.write(report + "\n")
            f.write("EOF\n")
