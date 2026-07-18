from dotenv import load_dotenv
load_dotenv()
import requests
import db

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}

targets = {
    "BAHub": "https://www.producthunt.com/r/7PQJEMLWRPKHBS?utm_campaign=producthunt-api&utm_medium=api-v2&utm_source=Application%3A+site+%28ID%3A+293430%29",
    "Bonacci Studio ": "https://www.producthunt.com/r/7LDWWV7Z4YLMAS?utm_campaign=producthunt-api&utm_medium=api-v2&utm_source=Application%3A+site+%28ID%3A+293430%29",
    "WallTrust": "https://www.producthunt.com/r/WC6GTYTXRX3UCX?utm_campaign=producthunt-api&utm_medium=api-v2&utm_source=Application%3A+site+%28ID%3A+293430%29",
}

conn = db.get_connection()
for name, url in targets.items():
    try:
        r = requests.get(url, timeout=10, allow_redirects=True, headers=HEADERS)
        clean_url = r.url.strip().replace("%20", "")  # bazi PH kayitlarinda hedef domainde bosluk hatasi var
        print(name, "->", repr(clean_url), "| status:", r.status_code)
        row = conn.execute("SELECT id FROM products WHERE original_name = ?", (name,)).fetchone()
        if row:
            pid = dict(row)["id"]
            conn.execute("UPDATE products SET website = ? WHERE id = ?", (clean_url, pid))
    except Exception as e:
        print(name, "-> HATA:", type(e).__name__, str(e)[:120])
conn.commit()
conn.close()
