# Local Web Crawler

This project implements a single-machine web crawler that supports concurrent indexing and search using only Python standard libraries.

The system exposes three main capabilities:
- Indexing: crawl from a given origin up to depth k while avoiding duplicate URLs
- Search: return relevant URLs as (relevant_url, origin_url, depth) triples
- Status: expose internal state including queue depth, worker activity, and crawl progress

The crawler is designed to allow search queries to run while indexing is still active. This is achieved by persisting crawl results in SQLite using WAL mode, enabling concurrent reads and writes.

Backpressure is implemented using a bounded in-memory queue, worker limits, and per-worker rate control. The system also persists frontier state, allowing unfinished crawl jobs to resume after restart.

The implementation intentionally prioritizes clarity and correctness within a single-node environment, while outlining clear paths toward production scaling in the accompanying recommendation document.

A localhost-runnable web crawler with three core capabilities:

- `index(origin, depth)` to crawl a site up to a maximum hop depth
- `search(query)` to return relevant URLs as `(relevant_url, origin_url, depth)` triples
- `status()` to inspect crawler progress, queue depth, and backpressure-related state

The implementation is intentionally built mostly with Python standard library functionality:
- `http.server` for the HTTP API
- `urllib` for fetching pages
- `html.parser` for extracting links
- `sqlite3` for persistence and search index storage
- `threading` and `queue` for concurrent indexing and bounded in-memory work scheduling

## Features

- Avoids crawling the same normalized URL more than once per running process
- Supports bounded queue size for basic backpressure
- Uses SQLite in WAL mode so search can run while indexing is active
- Stores crawl jobs, discoveries, pages, frontier state, and inverted index data
- Can resume unfinished frontier entries from the database when restarted
- Provides both CLI and HTTP endpoints
- Includes a minimal browser UI on `/`

## Project Structure

```text
crawler/
  __init__.py
  cli.py
  crawler.py
  search.py
  server.py
  storage.py
README.md
product_prd.md
recommendation.md