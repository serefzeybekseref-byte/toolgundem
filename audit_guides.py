# -*- coding: utf-8 -*-
"""
Rehber Kalite Denetleme Sistemi.

Her gun calisir, veritabanindaki TUM rehberleri (hem eskiden var olanlar hem
yeni uretilenler - fark etmez, hepsi ayni standarda tabi) objektif, deterministik
bir puanlamayla (0-100) degerlendirir. Puanlama iki katmandan olusur:

1) YAPISAL TAMLIK (bu script'e ozel): rehberin beklenen 8 bolumunun
   (kisa cevap, ogrenecekleriniz, neden-AI, adimlar, arac kartlari >=2,
   ucretsiz alternatif, hatalar, SSS >=3 soru) gercekten var olup olmadigini
   HTML icinde arar. Eksik bolum = puan kaybi.
2) quality_gate.check_guide() (mevcut, uretim sirasinda zaten kullanilan kapi):
   baslik/meta/kelime sayisi/eslesen arac sayisi/eski yil/tekrar eden cumle
   gibi icerik kalitesi sorunlarini tespit eder.

Esigin (75) altinda kalan rehberler icin OTOMATIK YENIDEN URETIM dener:
guides tablosundaki related_topic/related_comparison_slugs/related_tool_slugs
alanlarindan orijinal "guide_cfg"yi yeniden kurup generate_guide.run_one() ile
ayni slug uzerine (upsert) tazeler - bu, uretim sirasinda kullanilan AYNI
kalite kapisindan tekrar gecer.

Gunluk API/zaman butcesini asmamak icin bir calistirmada en fazla MAX_FIXES_PER_RUN
rehber duzeltilir (geri kalanlar bir sonraki gunun calistirmasinda ele alinir).

Kullanim: python audit_guides.py [--dry-run] [--max-fixes N]
"""
import sys
import re
import time
from dotenv import load_dotenv
load_dotenv()

MAX_FIXES_PER_RUN = 4
SCORE_THRESHOLD = 75

STRUCTURAL_CHECKS = [
    ("guide-quick-answer", "kisa-cevap-kutusu-eksik", 12),
    ("guide-learn-box", "ogrenecekleriniz-kutusu-eksik", 8),
    ("guide-benefits", "neden-yapay-zeka-bolumu-eksik", 10),
    ("guide-steps", "adim-adim-bolumu-eksik", 15),
    ('id="ucretsiz"', "ucretsiz-alternatifler-bolumu-eksik", 10),
    ("guide-mistakes", "sik-yapilan-hatalar-bolumu-eksik", 10),
]


def compute_guide_score(guide: dict) -> tuple:
    """
    Rehberin yapisal tamligini + icerik kalitesini objektif olarak puanlar.
    Donen: (score: int 0-100, issues: list[str])
    """
    html = guide.get("content_html") or ""
    issues = []
    score = 0

    for marker, issue_label, points in STRUCTURAL_CHECKS:
        if marker in html:
            score += points
        else:
            issues.append(issue_label)

    # Arac kartlari - en az 2 tane olmali (ana icerik degeri burada)
    tool_card_count = html.count("guide-tool-card")
    if tool_card_count >= 2:
        score += 20
    elif tool_card_count == 1:
        score += 8
        issues.append(f"sadece-{tool_card_count}-arac-karti-var-en-az-2-gerekli")
    else:
        issues.append("hic-arac-karti-yok")

    # SSS - id="sss" sonrasi en az 3 <h3> (soru) olmali
    sss_idx = html.find('id="sss"')
    if sss_idx != -1:
        sss_section = html[sss_idx:]
        h3_count = len(re.findall(r"<h3>", sss_section))
        if h3_count >= 3:
            score += 15
        elif h3_count > 0:
            score += 6
            issues.append(f"sss-bolumunde-sadece-{h3_count}-soru-var-en-az-3-gerekli")
        else:
            issues.append("sss-bolumu-bos")
    else:
        issues.append("sss-bolumu-hic-yok")

    # quality_gate.check_guide() - mevcut, uretimde kullanilan kapi
    try:
        from quality_gate import check_guide
        word_count = len((html or "").split())
        related_slugs = [s for s in (guide.get("related_tool_slugs") or "").split(",") if s.strip()]
        ok, gate_problems = check_guide(
            guide.get("title", ""), guide.get("meta_description", ""),
            html, word_count, related_slugs
        )
        for p in gate_problems:
            issues.append(f"kalite-kapisi: {p}")
    except Exception as e:
        issues.append(f"kalite-kapisi-calistirilamadi: {e}")

    return max(0, min(100, score)), issues


def _rebuild_guide_cfg(guide: dict) -> dict:
    """
    guides tablosundaki kalici alanlardan (tools_json YOK, ama related_topic /
    related_comparison_slugs / related_tool_slugs VAR) orijinal uretim
    konfigurasyonunu yeniden kurar - boylece ayni rehberi (ayni slug'a upsert
    ile) yeniden uretebiliriz.
    """
    from db import get_connection

    cfg = {
        "slug": guide["slug"],
        "title": guide["title"],
        "related_topic": guide.get("related_topic") or "",
        "comparison_slug": None,
        "manual_tools": None,
        "related_comparisons": [],
    }

    comp_slugs = [s for s in (guide.get("related_comparison_slugs") or "").split(",") if s.strip()]
    tool_slugs = [s for s in (guide.get("related_tool_slugs") or "").split(",") if s.strip()]

    if comp_slugs:
        cfg["comparison_slug"] = comp_slugs[0]
        cfg["related_comparisons"] = comp_slugs
        return cfg

    if tool_slugs:
        conn = get_connection()
        manual_tools = []
        for slug in tool_slugs:
            row = conn.execute(
                "SELECT original_name, summary_tr, why_use_it, pricing_type FROM products WHERE slug = ?",
                (slug,)
            ).fetchone()
            if row:
                r = dict(row)
                manual_tools.append({
                    "name": r["original_name"],
                    "best_for": (r.get("why_use_it") or r.get("summary_tr") or "")[:120],
                    "pricing": r.get("pricing_type") or "Bilinmiyor",
                })
        conn.close()
        if manual_tools:
            cfg["manual_tools"] = manual_tools
            return cfg

    return None  # yeniden kurulamadi - ic bilgi yetersiz, manuel bakilmali


def run_audit(dry_run: bool = False, max_fixes: int = MAX_FIXES_PER_RUN):
    from db import get_connection, get_all_guides

    guides = get_all_guides()
    print(f"Toplam {len(guides)} rehber denetleniyor...\n")

    results = []
    for g in guides:
        score, issues = compute_guide_score(g)
        results.append((g, score, issues))
        status = "OK" if score >= SCORE_THRESHOLD else "DUSUK"
        print(f"[{status}] {g['slug']} -> puan: {score}/100" + (f" | sorunlar: {', '.join(issues)}" if issues else ""))

    low_quality = [r for r in results if r[1] < SCORE_THRESHOLD]
    print(f"\n{len(low_quality)} rehber esigin ({SCORE_THRESHOLD}) altinda.")

    if dry_run or not low_quality:
        return {"audited": len(guides), "low_quality": len(low_quality), "fixed": 0}

    fixed = 0
    skipped_no_cfg = []
    for g, score, issues in low_quality:
        if fixed >= max_fixes:
            print(f"\nGunluk duzeltme limitine ({max_fixes}) ulasildi, kalanlar yarina birakildi.")
            break
        cfg = _rebuild_guide_cfg(g)
        if not cfg:
            skipped_no_cfg.append(g["slug"])
            continue
        print(f"\n[DUZELTILIYOR] {g['slug']} (puan: {score}) ...")
        try:
            from generate_guide import run_one
            ok, problems = run_one(cfg, validate=True)
            if ok:
                fixed += 1
                print(f"  -> basarili, yeniden uretildi.")
            else:
                print(f"  -> kalite kapisinda yine reddedildi: {problems}")
        except Exception as e:
            print(f"  -> HATA: {e}")
        time.sleep(3)

    if skipped_no_cfg:
        print(f"\nYeniden kurulamayan (manuel bakim gerekebilir): {', '.join(skipped_no_cfg)}")

    return {"audited": len(guides), "low_quality": len(low_quality), "fixed": fixed}


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    mf = MAX_FIXES_PER_RUN
    if "--max-fixes" in sys.argv:
        idx = sys.argv.index("--max-fixes")
        mf = int(sys.argv[idx + 1])
    summary = run_audit(dry_run=dry, max_fixes=mf)
    print(f"\nOZET: {summary}")
