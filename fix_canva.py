from dotenv import load_dotenv
load_dotenv()
import requests
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
r = requests.get("https://www.canva.com", timeout=10, allow_redirects=True, headers=HEADERS)
print(r.status_code, r.url)

import db
conn = db.get_connection()
conn.execute("UPDATE products SET website = ?, is_broken = 0 WHERE original_name = ?", ("https://www.canva.com", "Canva AI (Magic Studio)"))
conn.commit()
conn.close()
print("Guncellendi.")
