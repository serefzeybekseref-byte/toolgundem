# -*- coding: utf-8 -*-
"""
20 urunde tespit edilen yabanci dil sizintisini (Cince/Rusca/Japonca karakterler)
temizler. Orijinal Ingilizce veri saklanmadigi icin, mevcut Turkce metni referans
alip sadece yabanci kelimeleri temizleyen bir "duzeltme" cagrisi yapar (sifirdan
uretim degil - anlam/veri tutarliligini bozmadan).
"""
from dotenv import load_dotenv
load_dotenv()
import json
from generate_content import _generate_with_fallback
import db

FLAGGED_IDS = [437, 355, 71, 93, 276, 250, 300, 290, 426, 427, 186, 139, 251, 227, 198]


def clean_text_field(field_name: str, text: str) -> str:
    if not text or not text.strip():
        return text
    prompt = f"""Asagidaki Turkce metinde yanlislikla baska bir dilden (Cince, Rusca, Japonca vb.)
kelime/karakter karismis. Gorevin: metni ayni anlami koruyarak SADECE ve SADECE Turkce'ye
cevirmek/duzeltmek. Yabanci karakterleri Turkce karsiligiyla degistir. Metnin uzunlugunu ve
uslubunu olabildigince koru, sadece yabanci kelimeleri temizle.

Metin ({field_name}):
\"\"\"{text}\"\"\"

Su JSON formatinda cevap ver (baska hicbir sey yazma):
{{"duzeltilmis_metin": "..."}}
"""
    result = _generate_with_fallback(prompt, {"temperature": 0.3, "max_tokens": 1024, "response_format": {"type": "json_object"}})
    return result.get("duzeltilmis_metin", text)


def run():
    conn = db.get_connection()
    for pid in FLAGGED_IDS:
        row = conn.execute(
            "SELECT id, original_name, summary_tr, content_tr, why_use_it FROM products WHERE id = ?", (pid,)
        ).fetchone()
        if not row:
            continue
        d = dict(row)
        print(f"[{d['id']}] {d['original_name']} temizleniyor...")

        new_summary = clean_text_field("summary_tr", d["summary_tr"])
        new_content = clean_text_field("content_tr", d["content_tr"])
        new_why = clean_text_field("why_use_it", d["why_use_it"]) if d.get("why_use_it") else d.get("why_use_it")

        conn.execute(
            "UPDATE products SET summary_tr = ?, content_tr = ?, why_use_it = ? WHERE id = ?",
            (new_summary, new_content, new_why, d["id"])
        )
        conn.commit()
        print(f"  -> temizlendi.")

    conn.close()
    print("\nTum urunler islendi.")


if __name__ == "__main__":
    run()
