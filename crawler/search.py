def search(db, query: str, limit: int = 50):
    terms = [t.strip().lower() for t in query.split() if t.strip()]
    if not terms:
        return []

    score_by_url = {}

    for term in terms:
        rows = db.execute("""
            SELECT url, freq
            FROM inverted_index
            WHERE term = ?
        """, (term,)).fetchall()

        for url, freq in rows:
            score_by_url[url] = score_by_url.get(url, 0) + freq

    if not score_by_url:
        return []

    ranked_urls = sorted(score_by_url.items(), key=lambda x: (-x[1], x[0]))

    results = []
    seen = set()

    for url, _score in ranked_urls:
        discovery_rows = db.execute("""
            SELECT origin, depth
            FROM discoveries
            WHERE url = ?
            ORDER BY depth ASC, origin ASC
        """, (url,)).fetchall()

        for origin, depth in discovery_rows:
            triple = (url, origin, depth)
            if triple not in seen:
                seen.add(triple)
                results.append(triple)
                if len(results) >= limit:
                    return results

    return results