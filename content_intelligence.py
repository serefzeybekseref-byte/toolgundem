import json
from datetime import datetime, timedelta
from db import get_connection, init_db, slugify

def calculate_priority_score(clicks, searches, multi_clicks, orphan_bonus, penalty):
    """
    Priority Score = (clicks * 5) + (searches * 4) + (multi_clicks * 3) + (orphan_bonus) - (penalty)
    """
    total = (clicks * 5) + (searches * 4) + (multi_clicks * 3) + orphan_bonus - penalty
    return {
        "clicks": clicks,
        "searches": searches,
        "multi_clicks": multi_clicks,
        "orphan_bonus": orphan_bonus,
        "penalty": penalty,
        "total": max(0, total)
    }

def discover_opportunities():
    """
    1. Son 30 gunluk click, search, trend verilerini toplar.
    2. Guide/Comparison/Collection eksiklerini tespit eder.
    3. Eski rehberleri (180+ gun) Refresh icin belirler.
    4. Her firsat icin content_tasks tablosuna PENDING durumunda satir ekler.
    """
    init_db()
    conn = get_connection()
    now = datetime.utcnow()
    t_30d = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t_180d = (now - timedelta(days=180)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. Urun bazinda son 30 gunluk genel metrikleri cek (Click, Search)
    stats_query = """
        SELECT 
            p.id as product_id,
            p.slug,
            p.original_name,
            p.affiliate_url,
            p.topics,
            COUNT(e.id) as total_clicks,
            SUM(CASE WHEN e.referrer LIKE '%/ara%' THEN 1 ELSE 0 END) as search_clicks
        FROM products p
        JOIN outbound_click_events e ON p.id = e.product_id
        WHERE e.clicked_at >= ?
        GROUP BY p.id, p.slug, p.original_name, p.affiliate_url, p.topics
        HAVING COUNT(e.id) > 0
    """
    products_stats = conn.execute(stats_query, (t_30d,)).fetchall()

    # Zaten var olan rehberleri (guides) ogren
    guides = conn.execute("SELECT related_tool_slugs, created_at, slug as guide_slug FROM guides").fetchall()
    covered_in_guides = {} # product_slug -> {created_at, guide_slug}
    for g in guides:
        for s in (g["related_tool_slugs"] or "").split(","):
            s = s.strip()
            if s:
                covered_in_guides[s] = {"created_at": g["created_at"], "guide_slug": g["guide_slug"]}

    # Var olan karsilastirmalari ogren (comparisons)
    comparisons = conn.execute("SELECT id, slug, updated_at FROM comparisons").fetchall()
    
    # 2. Multi-click session analizi (Ayni session'da tiklanan ikililer)
    multi_clicks_query = """
        SELECT session_id, product_id, original_name, slug 
        FROM outbound_click_events e
        JOIN products p ON e.product_id = p.id
        WHERE session_id IS NOT NULL AND e.clicked_at >= ?
    """
    session_events = conn.execute(multi_clicks_query, (t_30d,)).fetchall()
    session_map = {}
    for ev in session_events:
        sid = ev["session_id"]
        if sid not in session_map:
            session_map[sid] = []
        if ev["product_id"] not in [p["product_id"] for p in session_map[sid]]:
            session_map[sid].append(dict(ev))

    pair_counts = {}
    for sid, prods in session_map.items():
        if len(prods) > 1:
            for i in range(len(prods)):
                for j in range(i + 1, len(prods)):
                    p1, p2 = prods[i], prods[j]
                    # Alfabetik sirala (A vs B)
                    slugs = sorted([p1["slug"], p2["slug"]])
                    pair_key = tuple(slugs)
                    if pair_key not in pair_counts:
                        pair_counts[pair_key] = {"count": 0, "p1": p1, "p2": p2}
                    pair_counts[pair_key]["count"] += 1

    tasks_to_insert = []

    # A. Guide, Affiliate, Refresh Firsatlari
    for p in products_stats:
        pid = p["product_id"]
        slug = p["slug"]
        clicks = p["total_clicks"]
        searches = p["search_clicks"]
        
        # Affiliate Firsati
        if not p["affiliate_url"]:
            score_data = calculate_priority_score(clicks, searches, 0, orphan_bonus=10, penalty=0)
            reason = f"Affiliate yok ({clicks} tiklama)"
            tasks_to_insert.append((pid, "AFFILIATE", score_data, reason))
            
        # Guide/Refresh Firsati
        if slug in covered_in_guides:
            g_created = covered_in_guides[slug]["created_at"]
            if g_created and g_created < t_180d:
                # Refresh Firsati
                score_data = calculate_priority_score(clicks, searches, 0, orphan_bonus=0, penalty=0)
                reason = f"Rehber 180 gunden eski ({clicks} tiklama)"
                tasks_to_insert.append((pid, "REFRESH", score_data, reason))
        else:
            # Guide Firsati (Orphan)
            score_data = calculate_priority_score(clicks, searches, 0, orphan_bonus=20, penalty=0)
            reason = f"Rehber yok ({clicks} tiklama)"
            tasks_to_insert.append((pid, "GUIDE", score_data, reason))

    # B. Comparison Firsatlari
    existing_comp_slugs = {c["slug"] for c in comparisons}
    for pair, data in pair_counts.items():
        p1 = data["p1"]
        p2 = data["p2"]
        count = data["count"]
        comp_slug = f"{p1['slug']}-vs-{p2['slug']}"
        
        if comp_slug not in existing_comp_slugs:
            score_data = calculate_priority_score(clicks=count, searches=0, multi_clicks=count, orphan_bonus=15, penalty=0)
            reason = f"Ayni oturumda {count} kez kiyaslandi: {p1['original_name']} vs {p2['original_name']}"
            tasks_to_insert.append((p1["product_id"], "COMPARISON", score_data, reason))
            
    # C. Kuyruga Yaz (Eger zaten ayni product_id ve task_type bekliyorsa guncelle, yoksa ekle)
    for pid, task_type, score_data, reason in tasks_to_insert:
        score_json = json.dumps(score_data)
        total_score = score_data["total"]
        
        existing = conn.execute(
            "SELECT id FROM content_tasks WHERE product_id = ? AND task_type = ? AND status IN ('PENDING', 'FAILED')", 
            (pid, task_type)
        ).fetchone()
        
        if existing:
            conn.execute("""
                UPDATE content_tasks 
                SET priority_score = ?, score_details = ?, reason = ?
                WHERE id = ?
            """, (total_score, score_json, reason, existing["id"]))
        else:
            conn.execute("""
                INSERT INTO content_tasks (product_id, task_type, status, priority_score, score_details, reason, created_at)
                VALUES (?, ?, 'PENDING', ?, ?, ?, ?)
            """, (pid, task_type, total_score, score_json, reason, now.isoformat()))
            
    conn.commit()
    conn.close()
    
    print(f"Priority Refresh tamamlandi. {len(tasks_to_insert)} firsat analiz edildi.")

if __name__ == "__main__":
    discover_opportunities()
