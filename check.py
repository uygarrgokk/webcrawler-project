import sqlite3

conn = sqlite3.connect("crawler.db")
cur = conn.cursor()

rows = cur.execute("""
SELECT ii.term, ii.url, d.origin, d.depth, ii.freq
FROM inverted_index ii
JOIN discoveries d ON d.url = ii.url
WHERE ii.term = 'wikipedia'
LIMIT 3
""").fetchall()

for r in rows:
    print(r)