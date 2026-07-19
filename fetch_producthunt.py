"""
AŞAMA 4: Product Hunt'tan en son ürünü çeken script.
Product Hunt GraphQL API v2 kullanılıyor (Developer Token ile).
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("PRODUCTHUNT_TOKEN")
API_URL = "https://api.producthunt.com/v2/api/graphql"

QUERY = """
query($cursor: String) {
  posts(first: 20, order: RANKING, after: $cursor, topic: "artificial-intelligence") {
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      node {
        id
        name
        tagline
        description
        url
        website
        votesCount
        thumbnail {
          url
        }
        media {
          url
          type
          videoUrl
        }
        topics(first: 5) {
          edges {
            node {
              name
            }
          }
        }
      }
    }
  }
}
"""

MAX_PRODUCTS = 50  # taşınabilecek makul maksimum (API rate limit + kalite dengesi)


def get_latest_products(max_products: int = MAX_PRODUCTS):
    """Product Hunt'in gunluk leaderboard siralamasina (RANKING) gore urunleri ceker.
    Sayfalama (cursor) ile max_products'a kadar toplar."""
    if not TOKEN:
        raise ValueError("PRODUCTHUNT_TOKEN bulunamadi. .env dosyasini kontrol et.")

    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }

    products = []
    cursor = None

    while len(products) < max_products:
        variables = {"cursor": cursor}
        response = requests.post(
            API_URL, json={"query": QUERY, "variables": variables}, headers=headers, timeout=30
        )
        response.raise_for_status()
        data = response.json()

        if "errors" in data:
            raise RuntimeError(f"Product Hunt API hatasi: {data['errors']}")

        page = data["data"]["posts"]
        edges = page["edges"]
        if not edges:
            break

        for edge in edges:
            node = edge["node"]
            topics = [t["node"]["name"] for t in node["topics"]["edges"]]
            # Sadece resim tipi medyayi galeri olarak al (video haric), max 4 tane
            gallery = [
                m["url"] for m in node.get("media", [])
                if m.get("type") == "image" and m.get("url")
            ][:4]
            products.append({
                "id": node["id"],
                "name": node["name"],
                "tagline": node["tagline"],
                "description": node.get("description", ""),
                "url": node["url"],
                "website": node.get("website", ""),
                "votes": node["votesCount"],
                "thumbnail": node["thumbnail"]["url"] if node.get("thumbnail") else None,
                "gallery": gallery,
                "topics": topics,
            })
            if len(products) >= max_products:
                break

        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    return products


if __name__ == "__main__":
    products = get_latest_products()
    for p in products:
        print(f"\n>> {p['name']} ({p['votes']} oy)")
        print(f"   {p['tagline']}")
        print(f"   Konular: {', '.join(p['topics'])}")
        print(f"   Link: {p['url']}")
