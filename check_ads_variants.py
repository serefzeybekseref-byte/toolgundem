import requests

urls = [
    "https://bulurumai.com/ads.txt",
    "https://www.bulurumai.com/ads.txt",
    "http://bulurumai.com/ads.txt",
    "http://www.bulurumai.com/ads.txt",
]

for u in urls:
    try:
        r = requests.get(u, timeout=15, allow_redirects=True)
        print(u, "->", r.status_code, "| final url:", r.url)
        print("   content-type:", r.headers.get("content-type"))
        print("   body:", r.text[:100].strip())
    except Exception as e:
        print(u, "-> HATA:", e)
    print()
