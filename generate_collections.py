import os
import json
import sqlite3
import requests
from dotenv import load_dotenv
from db import slugify

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    print("Error: GROQ_API_KEY not found in .env")
    exit(1)

DB_PATH = "products.db"

def get_all_products():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, title_tr, summary_tr, topics FROM products WHERE summary_tr IS NOT NULL LIMIT 40").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def create_collections_via_groq():
    products = get_all_products()
    if not products:
        print("No products found.")
        return
        
    product_list_text = ""
    for p in products:
        product_list_text += f"- ID: {p['id']} | İsim: {p['title_tr']} | Özet: {p['summary_tr']}\n"

    prompt = f"""
Sen ToolGündem için içerik üreten kıdemli bir editörsün.
Aşağıdaki yapay zeka araçlarını kullanarak 3 adet "Hazır Çözüm Paketi / Koleksiyon (Toolkit)" oluştur.
Örneğin: "Youtuber Toolkit", "Yazılımcılar İçin Başlangıç Paketi".

Kesinlikle JSON formatında yanıt ver. Başka bir şey yazma. JSON formatı:
[
  {{
    "title": "Koleksiyon Başlığı",
    "description": "Bu koleksiyon neden var? (1 cümle)",
    "items": [
      {{
        "product_id": (listeden ID),
        "reason": "Neden seçtin? (1 cümle)"
      }}
    ]
  }}
]

Her koleksiyonda 4-6 arası araç olsun.
İşte Araçlar:
{product_list_text}
"""

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "response_format": {"type": "json_object"}
    }
    
    # We must explicitly ask for a JSON object containing a list, so we modify prompt slightly
    payload["messages"][0]["content"] = prompt.replace("[\n  {\n", "{\n  \"collections\": [\n    {\n")

    print("Groq API'ye istek gönderiliyor...")
    try:
        resp = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
        if resp.status_code != 200:
            print(f"Groq error: {resp.text}")
            return
            
        result = resp.json()
        content = result['choices'][0]['message']['content']
        data = json.loads(content)
        
        collections = data.get("collections", [])
        print(f"{len(collections)} koleksiyon başarıyla üretildi. Kaydediliyor...")
        
        conn = sqlite3.connect(DB_PATH)
        for col in collections:
            slug = slugify(col["title"])
            exists = conn.execute("SELECT id FROM collections WHERE slug = ?", (slug,)).fetchone()
            if exists:
                print(f"Atlanıyor, '{col['title']}' zaten var.")
                continue
            
            cur = conn.execute(
                "INSERT INTO collections (slug, title, description) VALUES (?, ?, ?)",
                (slug, col["title"], col["description"])
            )
            collection_id = cur.lastrowid
            
            order = 1
            for item in col.get("items", []):
                try:
                    conn.execute(
                        "INSERT INTO collection_items (collection_id, product_id, order_num, reason) VALUES (?, ?, ?, ?)",
                        (collection_id, int(item["product_id"]), order, item.get("reason", ""))
                    )
                    order += 1
                except Exception as e:
                    pass
                    
        conn.commit()
        conn.close()
        print("İşlem tamamlandı!")
        
    except Exception as e:
        print(f"Hata oluştu: {e}")

if __name__ == "__main__":
    create_collections_via_groq()
