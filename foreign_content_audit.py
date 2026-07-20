# -*- coding: utf-8 -*-
"""
Sprint: Icerik Sagligi - Script 1/2
Yabanci dil sizintisi + ic tutarlilik denetimi. LLM KULLANMAZ (deterministik, ucretsiz, hizli).
"""
import re
from dotenv import load_dotenv
load_dotenv()
import db

# Meru teknik terimler / marka adlari - yanlis pozitif olmasin diye whitelist.
# NOT: Bu kelimeler regex'ten degil, "uzun ingilizce blok" tespitinden muaf tutulur.
WHITELIST_TERMS = {
    "openai", "github", "anthropic", "claude", "canva", "notion", "api", "sdk",
    "json", "python", "javascript", "chatgpt", "gemini", "groq", "nvidia",
    "ios", "android", "saas", "ai", "url", "html", "css", "app", "web",
    "chrome", "firefox", "safari", "windows", "macos", "linux", "cloud",
    "freemium", "premium", "pro", "beta", "mvp", "ui", "ux", "seo", "crm",
}

FOREIGN_SCRIPT_PATTERN = re.compile(
    r'[\u4e00-\u9fff]'      # Cince
    r'|[\u3040-\u30ff]'     # Japonca (Hiragana/Katakana)
    r'|[\uac00-\ud7af]'     # Korece (Hangul)
    r'|[\u0400-\u04FF]'     # Kiril
    r'|[\u0600-\u06ff]'     # Arapca
    r'|[\u0e00-\u0e7f]'     # Tay dili
    r'|\b(thì|và|của|được|những|không|với|người|làm|này|cho|một|các|để|có|là|trong|khi)\b'  # Vietnamca
)

# 15+ ardisik Ingilizce kelime bloklari icin basit tespit (whitelist kelimeleri haric tutulur)
_ENGLISH_COMMON_WORDS = set("""
the a an is are was were be been being have has had do does did will would could
should may might must can this that these those with without for from to of in on
at by as it its it's you your yours we our ours they their theirs he his she her
and or but if then else when where why how what who whom which not no yes
""".split())


def _english_block_check(text: str) -> list:
    """15+ ardisik kelimenin cogunlugu (>%70) yaygin Ingilizce kelime/whitelist ise isaretle."""
    words = re.findall(r"[a-zA-Z']+", text)
    flags = []
    window = 15
    for i in range(0, max(0, len(words) - window + 1)):
        chunk = [w.lower() for w in words[i:i + window]]
        english_like = sum(1 for w in chunk if w in _ENGLISH_COMMON_WORDS or w in WHITELIST_TERMS)
        if english_like / window > 0.5:
            flags.append(" ".join(words[i:i + window]))
            break  # bir kere bulmasi yeterli, ayni urunu tekrar tekrar raporlama
    return flags


# --- Ic tutarlilik kurallari: alan <-> metin celiskisi ---
PRICE_PATTERN = re.compile(r"\$\d+(\.\d+)?|\d+\s?(tl|₺|usd|eur)\b", re.IGNORECASE)
IOS_MENTION = re.compile(r"\biOS\b|\biPhone\b|\biPad\b", re.IGNORECASE)
API_MENTION = re.compile(r"\bAPI\b", re.IGNORECASE)


def check_consistency(product: dict) -> list:
    issues = []
    text = " ".join(filter(None, [product.get("summary_tr", ""), product.get("content_tr", "")]))
    pricing_type = (product.get("pricing_type") or "").lower()
    platforms = (product.get("platforms") or "").lower()

    if "ücretsiz" in pricing_type and "ücretli" not in pricing_type:
        if PRICE_PATTERN.search(text):
            issues.append(f"pricing_type='Ücretsiz' ama metinde fiyat gecıyor: {PRICE_PATTERN.search(text).group(0)}")

    if "web" in platforms and "ios" not in platforms and "mobil" not in platforms:
        if IOS_MENTION.search(text):
            issues.append("platforms='Web' ama metinde iOS/iPhone gecıyor")

    return issues


def run_audit():
    conn = db.get_connection()
    rows = conn.execute(
        "SELECT id, original_name, slug, summary_tr, content_tr, why_use_it, pricing_type, platforms FROM products"
    ).fetchall()

    foreign_flagged = []
    english_flagged = []
    consistency_flagged = []

    for r in rows:
        d = dict(r)
        text = " ".join(filter(None, [d.get("summary_tr", ""), d.get("content_tr", ""), d.get("why_use_it", "")]))

        foreign_matches = [m.group(0) for m in FOREIGN_SCRIPT_PATTERN.finditer(text)]
        if foreign_matches:
            foreign_flagged.append((d["id"], d["original_name"], d["slug"], foreign_matches[:5]))
            db.add_audit_flag(d["id"], "foreign_language", conn=conn)
        else:
            db.resolve_audit_flag(d["id"], "foreign_language", conn=conn)

        eng_blocks = _english_block_check(text)
        if eng_blocks:
            english_flagged.append((d["id"], d["original_name"], d["slug"], eng_blocks[0]))
            db.add_audit_flag(d["id"], "long_english_block", conn=conn)
        else:
            db.resolve_audit_flag(d["id"], "long_english_block", conn=conn)

        cons_issues = check_consistency(d)
        if cons_issues:
            consistency_flagged.append((d["id"], d["original_name"], d["slug"], cons_issues))
            db.add_audit_flag(d["id"], "field_text_inconsistency", conn=conn)
        else:
            db.resolve_audit_flag(d["id"], "field_text_inconsistency", conn=conn)

    conn.commit()
    conn.close()

    print(f"Toplam tarama: {len(rows)} urun")
    print(f"  Yabanci dil sizintisi: {len(foreign_flagged)}")
    print(f"  Uzun Ingilizce blok: {len(english_flagged)}")
    print(f"  Ic tutarlilik sorunu: {len(consistency_flagged)}")

    with open("_audit_content_result.txt", "w", encoding="utf-8") as f:
        f.write("=== YABANCI DIL SIZINTISI ===\n")
        for pid, name, slug, matches in foreign_flagged:
            f.write(f"id={pid} | {name} | slug={slug} | ornekler={[repr(m) for m in matches]}\n")
        f.write("\n=== UZUN INGILIZCE BLOK ===\n")
        for pid, name, slug, block in english_flagged:
            f.write(f"id={pid} | {name} | slug={slug} | blok={block!r}\n")
        f.write("\n=== IC TUTARLILIK SORUNU ===\n")
        for pid, name, slug, issues in consistency_flagged:
            f.write(f"id={pid} | {name} | slug={slug} | sorunlar={issues}\n")

    print("Detaylar _audit_content_result.txt dosyasina yazildi.")
    return {
        "foreign": foreign_flagged,
        "english": english_flagged,
        "consistency": consistency_flagged,
    }


if __name__ == "__main__":
    run_audit()
