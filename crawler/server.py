from typing import cast
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import json
from crawler.storage import init_db, get_connection
from crawler.crawler import WebCrawler
from crawler.search import search


class CrawlerHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address, RequestHandlerClass, db_path, workers, queue_size, rate):
        super().__init__(server_address, RequestHandlerClass)
        init_db(db_path)
        self.db_path = db_path
        self.crawler = WebCrawler(
            db_path=db_path,
            max_workers=workers,
            max_queue=queue_size,
            rate=rate,
        )


class Handler(BaseHTTPRequestHandler):
    @property
    def app_server(self):
        return cast(CrawlerHTTPServer, self.server)
    def _send_json(self, status_code, payload):
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_static(self, file_path, content_type):
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self._send_json(404, {"error": "file not found"})

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.serve_static("web/index.html", "text/html")
            return

        if parsed.path == "/status":
            payload = self.app_server.crawler.status()
            self._send_json(200, payload)
            return

        if parsed.path == "/search":
            params = parse_qs(parsed.query)
            query = params.get("q", [""])[0].strip()
            limit_raw = params.get("limit", ["50"])[0]

            try:
                limit = int(limit_raw)
            except ValueError:
                self._send_json(400, {"error": "limit must be an integer"})
                return

            conn = get_connection(self.app_server.db_path)
            try:
                results = search(conn, query, limit=limit)
            finally:
                conn.close()

            payload = {
                "query": query,
                "count": len(results),
                "results": results,
            }
            self._send_json(200, payload)
            return

        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/index":
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)

            try:
                data = json.loads(raw_body.decode("utf-8"))
            except Exception:
                self._send_json(400, {"error": "invalid json body"})
                return

            origin = data.get("origin")
            depth = data.get("depth")

            if not isinstance(origin, str) or not origin.strip():
                self._send_json(400, {"error": "origin must be a non-empty string"})
                return

            if not isinstance(depth, int) or depth < 0:
                self._send_json(400, {"error": "depth must be a non-negative integer"})
                return

            try:
                job_id = self.app_server.crawler.crawl(origin.strip(), depth)
            except ValueError as e:
                self._send_json(400, {"error": str(e)})
                return
            except Exception as e:
                self._send_json(500, {"error": str(e)})
                return

            self._send_json(202, {
                "message": "index job accepted",
                "job_id": job_id,
                "origin": origin.strip(),
                "depth": depth,
            })
            return

        self._send_json(404, {"error": "not found"})

    def log_message(self, format, *args):
        return


def run_server(db_path="crawler.db", host="127.0.0.1", port=8080, workers=5, queue_size=1000, rate=5.0):
    server = CrawlerHTTPServer(
        (host, port),
        Handler,
        db_path=db_path,
        workers=workers,
        queue_size=queue_size,
        rate=rate,
    )
    print(f"Server running on http://{host}:{port}")
    server.serve_forever()