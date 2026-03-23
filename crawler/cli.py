import argparse

from crawler.storage import init_db, get_connection
from crawler.crawler import WebCrawler
from crawler.search import search
from crawler.server import run_server

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="crawler.db")

    sub = parser.add_subparsers(dest="cmd")

    server_cmd = sub.add_parser("server")
    server_cmd.add_argument("--workers", type=int, default=5)
    server_cmd.add_argument("--queue-size", type=int, default=1000)
    server_cmd.add_argument("--rate", type=float, default=5.0)

    index_cmd = sub.add_parser("index")
    index_cmd.add_argument("url")
    index_cmd.add_argument("depth", type=int)
    index_cmd.add_argument("--workers", type=int, default=5)
    index_cmd.add_argument("--queue-size", type=int, default=1000)
    index_cmd.add_argument("--rate", type=float, default=5.0)

    search_cmd = sub.add_parser("search")
    search_cmd.add_argument("query")
    search_cmd.add_argument("--limit", type=int, default=50)

    status_cmd = sub.add_parser("status")
    status_cmd.add_argument("--workers", type=int, default=5)
    status_cmd.add_argument("--queue-size", type=int, default=1000)
    status_cmd.add_argument("--rate", type=float, default=5.0)

    args = parser.parse_args()

    init_db(args.db)

    if args.cmd == "search":
        conn = get_connection(args.db)
        try:
            results = search(conn, args.query, limit=args.limit)
            print(results)
        finally:
            conn.close()
        return

    if args.cmd == "index":
        crawler = WebCrawler(
            db_path=args.db,
            max_workers=args.workers,
            max_queue=args.queue_size,
            rate=args.rate,
        )
        job_id = crawler.crawl(args.url, args.depth)
        print(f"started job_id={job_id}")
        crawler.queue.join()
        print("indexing completed")
        return

    if args.cmd == "status":
        crawler = WebCrawler(
            db_path=args.db,
            max_workers=args.workers,
            max_queue=args.queue_size,
            rate=args.rate,
        )
        print(crawler.status())
        return

    if args.cmd == "server":
        run_server(
            db_path=args.db,
            host="127.0.0.1",
            port=8080,
            workers=args.workers,
            queue_size=args.queue_size,
            rate=args.rate,
        )
        return
    
    parser.print_help()


if __name__ == "__main__":
    main()