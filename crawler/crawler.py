import threading
import queue
import time
import re
import sqlite3
import urllib.request
import urllib.error
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, urldefrag

from crawler.storage import get_connection, transaction


class LinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.links.append(value)


class WebCrawler:
    def __init__(self, db_path: str, max_workers: int = 5, max_queue: int = 1000, rate: float = 5.0):
        self.db_path = db_path
        self.max_workers = max_workers
        self.max_queue = max_queue
        self.rate = rate

        self.queue = queue.Queue(maxsize=max_queue)
        self.shutdown_event = threading.Event()
        self.lock = threading.Lock()

        self.visited_urls = set()
        self.active_workers = 0
        self.pages_indexed = 0
        self.pages_discovered = 0
        self.last_error = None

        self.workers = []
        for _ in range(max_workers):
            t = threading.Thread(target=self.worker_loop, daemon=True)
            t.start()
            self.workers.append(t)

        self.load_running_frontier()

    def log(self, conn, job_id, message, level="INFO"):
        conn.execute(
            "INSERT INTO logs (job_id, level, message) VALUES (?, ?, ?)",
            (job_id, level, message)
        )

    def normalize_url(self, base_url: str, raw_url: str):
        joined = urljoin(base_url, raw_url)
        joined, _frag = urldefrag(joined)

        parsed = urlparse(joined)
        if parsed.scheme not in ("http", "https"):
            return None

        netloc = parsed.netloc.lower()
        path = parsed.path or "/"

        normalized = f"{parsed.scheme}://{netloc}{path}"
        if parsed.query:
            normalized += f"?{parsed.query}"

        return normalized

    def extract_text_terms(self, html: str):
        return re.findall(r"[a-zA-Z0-9_]+", html.lower())

    def extract_links(self, html: str):
        parser = LinkExtractor()
        try:
            parser.feed(html)
        except Exception:
            return []
        return parser.links

    def fetch_page(self, url: str):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "LocalCrawler/1.0"
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if "text/html" not in content_type:
                return None
            raw = resp.read()
            return raw.decode("utf-8", errors="ignore")

    def load_running_frontier(self):
        conn = get_connection(self.db_path)
        rows = conn.execute("""
            SELECT job_id, url, depth
            FROM frontier
            WHERE status = 'pending'
            ORDER BY rowid ASC
        """).fetchall()
        conn.close()

        for job_id, url, depth in rows:
            if not self.queue.full():
                self.queue.put((job_id, url, depth))

    def start_job(self, origin: str, max_depth: int):
        conn = get_connection(self.db_path)

        with transaction(conn):
            cur = conn.execute("""
                INSERT INTO jobs (origin, max_depth, status)
                VALUES (?, ?, 'running')
            """, (origin, max_depth))
            
            job_id = cur.lastrowid
            self.log(conn, job_id, f"Started crawl for {origin} with depth {max_depth}") 

            conn.execute("""
                INSERT OR IGNORE INTO discoveries (job_id, url, origin, depth)
                VALUES (?, ?, ?, ?)
            """, (job_id, origin, origin, 0))

            conn.execute("""
                INSERT OR IGNORE INTO frontier (job_id, url, depth, status)
                VALUES (?, ?, 0, 'pending')
            """, (job_id, origin))

        conn.close()

        if not self.queue.full():
            self.queue.put((job_id, origin, 0))

        return job_id

    def crawl(self, origin: str, max_depth: int):
        normalized_origin = self.normalize_url(origin, origin)
        if not normalized_origin:
            raise ValueError("Invalid origin URL")
        return self.start_job(normalized_origin, max_depth)

    def mark_frontier_status(self, conn, job_id: int, url: str, status: str):
        conn.execute("""
            UPDATE frontier
            SET status = ?
            WHERE job_id = ? AND url = ?
        """, (status, job_id, url))

    def upsert_page_and_index(self, conn, url: str, html: str):
        conn.execute("""
            INSERT OR REPLACE INTO pages (url, content, fetched_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (url, html))

        term_freq = {}
        for term in self.extract_text_terms(html):
            term_freq[term] = term_freq.get(term, 0) + 1

        for term, freq in term_freq.items():
            conn.execute("""
                INSERT INTO inverted_index (term, url, freq)
                VALUES (?, ?, ?)
                ON CONFLICT(term, url)
                DO UPDATE SET freq = excluded.freq
            """, (term, url, freq))

    def enqueue_discovered_links(self, conn, job_id: int, origin: str, parent_url: str, parent_depth: int, html: str, max_depth: int):
        if parent_depth >= max_depth:
            return

        raw_links = self.extract_links(html)

        for raw_link in raw_links:
            normalized = self.normalize_url(parent_url, raw_link)
            if not normalized:
                continue

            next_depth = parent_depth + 1

            conn.execute("""
                INSERT OR IGNORE INTO discoveries (job_id, url, origin, depth)
                VALUES (?, ?, ?, ?)
            """, (job_id, normalized, origin, next_depth))

            conn.execute("""
                INSERT OR IGNORE INTO frontier (job_id, url, depth, status)
                VALUES (?, ?, ?, 'pending')
            """, (job_id, normalized, next_depth))

            if conn.total_changes > 0:
                with self.lock:
                    self.pages_discovered += 1

                if not self.queue.full():
                    self.queue.put((job_id, normalized, next_depth))

    def get_job(self, conn, job_id: int):
        row = conn.execute("""
            SELECT origin, max_depth, status
            FROM jobs
            WHERE job_id = ?
        """, (job_id,)).fetchone()
        return row

    def maybe_finish_job(self, conn, job_id: int):
        remaining = conn.execute("""
            SELECT COUNT(*)
            FROM frontier
            WHERE job_id = ? AND status IN ('pending', 'processing')
        """, (job_id,)).fetchone()[0]

        if remaining == 0:
            conn.execute("""
                UPDATE jobs
                SET status = 'completed'
                WHERE job_id = ?
            """, (job_id,))

    def worker_loop(self):
        conn = get_connection(self.db_path)

        while not self.shutdown_event.is_set():
            try:
                job_id, url, depth = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue

            with self.lock:
                self.active_workers += 1

            try:
                job_row = self.get_job(conn, job_id)
                if not job_row:
                    self.queue.task_done()
                    continue

                origin, max_depth, status = job_row
                if status != "running":
                    self.queue.task_done()
                    continue

                with self.lock:
                    if url in self.visited_urls:
                        with transaction(conn):
                            self.mark_frontier_status(conn, job_id, url, "done")
                            self.maybe_finish_job(conn, job_id)
                        self.queue.task_done()
                        self.active_workers -= 1
                        continue
                    self.visited_urls.add(url)

                with transaction(conn):
                    self.mark_frontier_status(conn, job_id, url, "processing")

                time.sleep(1.0 / self.rate)

                try:
                    html = self.fetch_page(url)
                except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as e:
                    self.last_error = str(e)
                    with transaction(conn):
                        self.mark_frontier_status(conn, job_id, url, "error")
                        self.maybe_finish_job(conn, job_id)
                    self.queue.task_done()
                    with self.lock:
                        self.active_workers -= 1
                    continue
                except Exception as e:
                    self.last_error = str(e)
                    with transaction(conn):
                        self.mark_frontier_status(conn, job_id, url, "error")
                        self.maybe_finish_job(conn, job_id)
                    self.queue.task_done()
                    with self.lock:
                        self.active_workers -= 1
                    continue

                if html is None:
                    with transaction(conn):
                        self.mark_frontier_status(conn, job_id, url, "done")
                        self.maybe_finish_job(conn, job_id)
                    self.queue.task_done()
                    with self.lock:
                        self.active_workers -= 1
                    continue

                with transaction(conn):
                    self.upsert_page_and_index(conn, url, html)
                    self.enqueue_discovered_links(conn, job_id, origin, url, depth, html, max_depth)
                    self.mark_frontier_status(conn, job_id, url, "done")
                    self.maybe_finish_job(conn, job_id)

                with self.lock:
                    self.pages_indexed += 1

            finally:
                with self.lock:
                    if self.active_workers > 0:
                        self.active_workers -= 1
                self.queue.task_done()

        conn.close()

    def status(self):
        conn = get_connection(self.db_path)

        jobs_running = conn.execute("""
            SELECT COUNT(*)
            FROM jobs
            WHERE status = 'running'
        """).fetchone()[0]

        jobs_completed = conn.execute("""
            SELECT COUNT(*)
            FROM jobs
            WHERE status = 'completed'
        """).fetchone()[0]

        frontier_pending = conn.execute("""
            SELECT COUNT(*)
            FROM frontier
            WHERE status = 'pending'
        """).fetchone()[0]

        frontier_processing = conn.execute("""
            SELECT COUNT(*)
            FROM frontier
            WHERE status = 'processing'
        """).fetchone()[0]

        frontier_done = conn.execute("""
            SELECT COUNT(*)
            FROM frontier
            WHERE status = 'done'
        """).fetchone()[0]

        frontier_error = conn.execute("""
            SELECT COUNT(*)
            FROM frontier
            WHERE status = 'error'
        """).fetchone()[0]

        total_pages = conn.execute("""
            SELECT COUNT(*)
            FROM pages
        """).fetchone()[0]

        total_discoveries = conn.execute("""
            SELECT COUNT(*)
            FROM discoveries
        """).fetchone()[0]

        conn.close()

        return {
            "jobs_running": jobs_running,
            "jobs_completed": jobs_completed,
            "queue_depth": self.queue.qsize(),
            "frontier_pending": frontier_pending,
            "frontier_processing": frontier_processing,
            "frontier_done": frontier_done,
            "frontier_error": frontier_error,
            "pages_indexed": total_pages,
            "pages_discovered": total_discoveries,
            "total_pages_in_db": total_pages,
            "active_workers": self.active_workers,
            "max_workers": self.max_workers,
            "backpressure_on": self.queue.qsize() >= self.max_queue,
            "rate_per_worker_per_sec": self.rate,
            "last_error": self.last_error,
        }