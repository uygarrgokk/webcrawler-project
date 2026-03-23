# Product PRD: Local Web Crawler

## Goal

Build a localhost-runnable web crawler that supports two core capabilities:

1. `index(origin, k)`
2. `search(query)`

The system should run on a single machine, use mostly language-native tools, and demonstrate clean architecture and controlled resource usage.

---

## Functional Requirements

### 1. Index

Given:
- `origin`: starting URL
- `k`: maximum crawl depth

The system must:
- crawl pages starting from origin
- follow links up to depth `k`
- avoid crawling the same URL twice
- store discovered pages and relationships
- track:
  - origin URL
  - discovery depth

---

### 2. Search

Given:
- `query`: string

Return:
- list of tuples:
(relevant_url, origin_url, depth)

Search should:
- work while indexing is active
- reflect newly indexed pages
- use a simple but reasonable relevance model

---

### 3. System State

The system must expose:

- running/completed jobs
- queue size
- pending/processing/done counts
- indexed pages
- discovered pages
- worker count
- backpressure state
- last error

---

### 4. Interface

The system should provide:

- CLI commands
- HTTP API
- simple browser UI

---

### 5. Resume (Nice to have)

The crawler should:
- persist frontier state
- continue unfinished jobs after restart

---

## Non-Functional Requirements

### Performance
- bounded queue (no memory explosion)
- concurrent workers
- rate limiting

### Reliability
- handle network errors safely
- not crash on bad pages
- maintain consistent DB state

### Simplicity
- use Python standard library where possible
- keep implementation readable

---

## Architecture

### Components

#### 1. HTTP Server
- `/index`
- `/search`
- `/status`

#### 2. Worker Pool
- multiple threads
- fetch pages
- parse links
- update DB

#### 3. Scheduler
- manages queue
- enforces limits

#### 4. Search Layer
- inverted index lookup
- simple ranking

#### 5. Storage (SQLite)

Tables:
- jobs
- pages
- discoveries
- inverted_index
- frontier

### Data Schema

- `jobs`:
  - `job_id` INTEGER PRIMARY KEY AUTOINCREMENT
  - `origin` TEXT NOT NULL
  - `max_depth` INTEGER NOT NULL
  - `status` TEXT NOT NULL DEFAULT 'running'
  - `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP

- `pages`:
  - `url` TEXT PRIMARY KEY
  - `content` TEXT
  - `fetched_at` DATETIME DEFAULT CURRENT_TIMESTAMP

- `discoveries`:
  - `job_id` INTEGER NOT NULL
  - `url` TEXT NOT NULL
  - `origin` TEXT NOT NULL
  - `depth` INTEGER NOT NULL
  - PRIMARY KEY (`job_id`, `url`)

- `inverted_index`:
  - `term` TEXT NOT NULL
  - `url` TEXT NOT NULL
  - `freq` INTEGER NOT NULL DEFAULT 1
  - PRIMARY KEY (`term`, `url`)

- `frontier`:
  - `job_id` INTEGER NOT NULL
  - `url` TEXT NOT NULL
  - `depth` INTEGER NOT NULL
  - `status` TEXT NOT NULL DEFAULT 'pending'
  - PRIMARY KEY (`job_id`, `url`)

---

## Relevance Model

- split query into terms
- find matching URLs
- sum term frequencies
- rank by score

---

## Backpressure

- bounded queue
- limited workers
- request rate control

---

## Resume Strategy

- store pending frontier in DB
- reload on startup

---

## Out of Scope

- robots.txt
- distributed crawling
- advanced ranking (BM25, PageRank)
- JS rendering
- authentication