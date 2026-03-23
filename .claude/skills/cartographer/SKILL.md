---
name: cartographer
description: >
  Cartographer skill for the Card Promotions Data Crawler — maps the multi-service architecture,
  generates diagrams, documents data flow, designs URL discovery and site-mapping features, and produces
  technical documentation. Use this skill whenever you need to understand the system topology, map
  service dependencies, visualize Docker Compose infrastructure, generate architecture diagrams,
  create API documentation, design frontier/URL graph features, document the crawl pipeline,
  or produce any technical overview. Trigger on: "map the system", "architecture diagram",
  "how does this work", "document this", "service diagram", "data flow", "system overview",
  "what talks to what", "Docker Compose topology", or any request to understand, visualize,
  or document the crawler's structure. Even "give me the big picture" or "how is this organized"
  should trigger this skill.
---

# Card Promotions Crawler — Cartographer Skill

You are the cartographer for the **Card Promotions Data Crawler**, a multi-service system that
crawls bank websites for credit card deals. Your job: map the service topology, design URL discovery
features, and produce clear documentation and diagrams.

## System Context

The system consists of 7 Docker Compose services communicating through Redis queues, with MinIO for
blob storage and Postgres for metadata + extracted deals. An LLM is used for relevance filtering
and structured deal extraction. A Puppeteer sidecar handles JavaScript-rendered pages.

## Three Domains

1. **Service Topology** — How the Docker Compose services connect, what each does, and how data
   flows between them through queues and shared storage.
2. **URL/Site Cartography** — The frontier queue design, URL dedup, link graph, domain boundary
   detection, and crawl scope management.
3. **Documentation & Diagrams** — Producing artifacts that communicate the above clearly.

---

## Domain 1: Service Topology

### Docker Compose Service Map

```mermaid
graph TB
    subgraph Infrastructure
        redis[(Redis)]
        postgres[(PostgreSQL)]
        minio[(MinIO)]
    end

    subgraph Services
        crawler[Crawler Service]
        parser[Parser Service]
        extractor[Extractor Service]
        api[API Service]
        puppeteer[Puppeteer Sidecar]
    end

    subgraph External
        banks[Bank Websites]
        llm_api[LLM API]
        webapp[Web App]
    end

    crawler -->|fetch HTML| banks
    crawler -->|store HTML| minio
    crawler -->|write URLMetadata| postgres
    crawler -->|rate limit, DNS cache, dedup| redis
    crawler -->|consume frontier queue| redis
    crawler -->|push to parsing queue| redis

    parser -->|consume parsing queue| redis
    parser -->|read HTML| minio
    parser -->|update URLMetadata| postgres
    parser -->|push new URLs to frontier| redis
    parser -->|relevance check| llm_api
    parser -->|render dynamic pages| puppeteer
    parser -->|push relevant pages to extraction queue| redis

    extractor -->|consume extraction queue| redis
    extractor -->|extract deals| llm_api
    extractor -->|write CreditCardDeal| postgres

    api -->|read deals| postgres
    webapp -->|GET /deals| api
```

### Service Responsibilities

| Service | Consumes | Produces | Dependencies |
|---------|----------|----------|--------------|
| **Crawler** | Frontier Queue (Redis) | Raw HTML (MinIO), URLMetadata (Postgres), Parsing Queue items | Redis, MinIO, Postgres |
| **Parser** | Parsing Queue (Redis) | New URLs → Frontier Queue, Relevant pages → Extraction Queue | Redis, MinIO, Postgres, Puppeteer, LLM API |
| **Extractor** | Extraction Queue (Redis) | CreditCardDeal records (Postgres) | Redis, Postgres, LLM API |
| **API** | HTTP requests | JSON responses | Postgres |
| **Puppeteer** | HTTP requests from Parser | Rendered HTML | None (stateless) |

### Redis Key Layout

Redis is used for multiple purposes. Document the key naming convention:

```
Queue keys:
  queue:frontier          — Frontier URL queue (Redis list)
  queue:parsing           — Crawler→Parser handoff (Redis list)
  queue:extraction        — Parser→Extractor handoff (Redis list)
  queue:dead_letter       — Failed messages (Redis list)

Deduplication:
  dedup:seen_urls         — Set of SHA256 hashes of normalized URLs

Rate limiting:
  ratelimit:{domain}      — Sliding window counter per domain (Redis sorted set or string with TTL)

DNS cache:
  dns:{hostname}          — Cached DNS resolution (string with TTL)

Stats:
  stats:fetched_count     — Total pages fetched (counter)
  stats:relevant_count    — Pages marked relevant (counter)
  stats:deals_count       — Deals extracted (counter)
```

### Postgres Schema

Two logical databases (or schemas within one database):

```sql
-- Crawl metadata
CREATE TABLE url_metadata (
    id              SERIAL PRIMARY KEY,
    url             TEXT NOT NULL UNIQUE,
    domain          TEXT NOT NULL,
    file_path       TEXT,                  -- MinIO object path
    status          TEXT NOT NULL DEFAULT 'queued',
    status_code     INTEGER,
    content_hash    TEXT,                  -- SHA256 of page content
    depth           INTEGER DEFAULT 0,
    retry_count     INTEGER DEFAULT 0,
    is_seed         BOOLEAN DEFAULT false,
    error_message   TEXT,
    discovered_at   TIMESTAMPTZ DEFAULT now(),
    fetched_at      TIMESTAMPTZ,
    parsed_at       TIMESTAMPTZ
);

CREATE INDEX idx_url_metadata_domain ON url_metadata(domain);
CREATE INDEX idx_url_metadata_status ON url_metadata(status);

-- Extracted deals
CREATE TABLE credit_card_deals (
    id                   SERIAL PRIMARY KEY,
    source_url           TEXT NOT NULL,
    bank_name            TEXT NOT NULL,
    card_name            TEXT,
    promotion_title      TEXT NOT NULL,
    description          TEXT NOT NULL,
    discount_percentage  NUMERIC(5,2),
    discount_amount      NUMERIC(10,2),
    merchant_name        TEXT,
    merchant_category    TEXT,
    valid_from           DATE,
    valid_until          DATE,
    terms_and_conditions TEXT,
    raw_text             TEXT,
    confidence_score     NUMERIC(3,2),
    extracted_at         TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_deals_bank ON credit_card_deals(bank_name);
CREATE INDEX idx_deals_category ON credit_card_deals(merchant_category);
CREATE INDEX idx_deals_valid_until ON credit_card_deals(valid_until);
```

### MinIO Bucket Layout

```
Bucket: pages
  pages/{domain}/{url_hash}.html     — Raw HTML of crawled pages
  pages/{domain}/{url_hash}.meta     — Optional: response headers, fetch timestamp

Bucket: screenshots (optional, for Puppeteer renders)
  screenshots/{domain}/{url_hash}.png
```

---

## Domain 2: URL/Site Cartography

### Data Flow — The Crawl Lifecycle

```mermaid
sequenceDiagram
    participant Seed as Seed URLs
    participant FQ as Frontier Queue
    participant Dedup as Dedup (Redis Set)
    participant Crawler as Crawler Service
    participant MinIO as MinIO
    participant PG as Postgres
    participant PQ as Parsing Queue
    participant Parser as Parser Service
    participant Pup as Puppeteer
    participant LLM as LLM API
    participant EQ as Extraction Queue
    participant Ext as Extractor Service
    participant DB as Deals DB

    Seed->>Dedup: Check if seen
    Dedup-->>FQ: New URLs only
    FQ->>Crawler: Pop URL (BRPOP)

    Crawler->>Crawler: Rate limit check
    Crawler->>Crawler: robots.txt check
    Crawler->>MinIO: Store HTML
    Crawler->>PG: Update URLMetadata (status=fetched)
    Crawler->>PQ: Push {url, minioPath}

    PQ->>Parser: Pop item (BRPOP)
    Parser->>MinIO: Fetch HTML
    alt Dynamic page
        Parser->>Pup: Render with Puppeteer
        Pup-->>Parser: Rendered HTML
    end
    Parser->>Parser: Extract text + links
    Parser->>Dedup: Check new URLs
    Dedup-->>FQ: Unseen URLs
    Parser->>Parser: URL pre-filter (patterns)
    Parser->>LLM: Relevance check (uncertain pages)
    LLM-->>Parser: is_relevant + confidence
    Parser->>PG: Update URLMetadata (status=relevant/irrelevant)

    alt Page is relevant
        Parser->>EQ: Push {url, text, title}
    end

    EQ->>Ext: Pop item
    Ext->>LLM: Extract structured deals
    LLM-->>Ext: CreditCardDeal[]
    Ext->>DB: Write deals
    Ext->>PG: Update URLMetadata (status=extracted)
```

### URL State Machine

```mermaid
stateDiagram-v2
    [*] --> Discovered: Found in page / seed list
    Discovered --> Dedup_Check: URL normalized

    state dedup <<choice>>
    Dedup_Check --> dedup
    dedup --> Rejected_Duplicate: Already seen
    dedup --> Queued: New URL → Frontier Queue

    Queued --> Fetching: Dequeued by crawler

    state fetch_result <<choice>>
    Fetching --> fetch_result
    fetch_result --> Fetched: HTTP 2xx
    fetch_result --> Failed: Error / timeout
    fetch_result --> Redirected: HTTP 3xx

    Redirected --> Discovered: New URL from redirect target
    Failed --> Queued: Retry (if retries < max)
    Failed --> Dead: Max retries exceeded

    Fetched --> Parsing: In parsing queue
    Parsing --> Parsed: Links + text extracted

    state relevance <<choice>>
    Parsed --> relevance: LLM or pre-filter
    relevance --> Relevant: Is a promo page
    relevance --> Irrelevant: Not a promo page

    Relevant --> Extracting: In extraction queue
    Extracting --> Extracted: Deals written to DB

    Extracted --> [*]
    Irrelevant --> [*]
    Dead --> [*]
    Rejected_Duplicate --> [*]
```

### Frontier Queue Design

```
Design Decisions:
├── Queue Backend: Redis List (LPUSH/BRPOP)
│   └── Upgrade path: Redis Streams for at-least-once delivery
├── Priority: FIFO by default
│   └── Seed URLs get higher priority (push to front)
│   └── Future: Redis Sorted Set (ZADD/BZPOPMIN) for priority scoring
├── Deduplication: Redis Set of SHA256(normalized_url)
│   └── Upgrade path: RedisBloom for memory efficiency at scale
├── Scope Boundaries:
│   ├── Domain whitelist (only crawl configured bank domains)
│   ├── URL pattern whitelist per domain
│   ├── Max depth from seed URL
│   └── Max URLs per domain
└── Persistence:
    ├── Redis AOF for queue durability (survives restart)
    └── URLMetadata in Postgres as source of truth for crawl state
```

### Domain Boundary Configuration

For a focused crawler targeting bank promotion pages, crawl scope is critical:

```python
# Example domain configuration
CRAWL_DOMAINS = {
    "bank-a.example.com": {
        "seed_urls": [
            "https://bank-a.example.com/promotions",
            "https://bank-a.example.com/credit-cards/offers",
        ],
        "url_patterns": [
            r"^https://bank-a\.example\.com/promotions/.*",
            r"^https://bank-a\.example\.com/credit-cards/.*",
            r"^https://bank-a\.example\.com/offers/.*",
        ],
        "exclude_patterns": [
            r"/careers", r"/investor", r"/login", r"/register",
        ],
        "max_depth": 4,
        "max_urls": 500,
        "needs_puppeteer": False,
    },
    "bank-b.example.com": {
        "seed_urls": ["https://bank-b.example.com/privileges"],
        "url_patterns": [r"^https://bank-b\.example\.com/privileges/.*"],
        "max_depth": 3,
        "max_urls": 300,
        "needs_puppeteer": True,  # This bank uses SPA
    },
}
```

---

## Domain 3: Documentation & Diagrams

### Diagram Formats

This project uses **two diagram formats** for different contexts:

| Context | Format | Why |
|---------|--------|-----|
| README / inline markdown | **Mermaid** | GitHub renders natively, no export step |
| Detailed architecture / interactive | **Excalidraw JSON** | Hand-drawn style, drag-and-drop editing, richer layouts |

Excalidraw source files live in `docs/diagrams/*.excalidraw`. Open them at excalidraw.com or the desktop app.

### When to Use Which

| Purpose | Format |
|---------|--------|
| Quick service topology in a PR description | Mermaid |
| Full architecture diagram with annotations | Excalidraw |
| Data flow sequence | Mermaid `sequenceDiagram` |
| Annotating changes to existing diagram | Excalidraw (green overlays) |
| Database ER diagram | Mermaid `erDiagram` |

---

### Excalidraw JSON Reference

When producing Excalidraw diagrams, output valid clipboard JSON that the user can paste directly into Excalidraw (Ctrl+V):

```json
{"type":"excalidraw/clipboard","elements":[...],"files":{}}
```

#### Element Types

| Type | Use for | Key properties |
|------|---------|----------------|
| `rectangle` | Services, queues, boxes | `x`, `y`, `width`, `height`, `strokeColor`, `roundness` |
| `ellipse` | Databases, storage | `x`, `y`, `width`, `height` |
| `arrow` | Connections, data flow | `points`, `startBinding`, `endBinding` |
| `text` | Labels, annotations | `text`, `fontSize`, `containerId` (for text inside shapes) |

#### Arrow Bindings

Connect arrows to shapes using bindings:

```json
{
  "type": "arrow",
  "startBinding": { "elementId": "shape-id", "focus": 0, "gap": 1 },
  "endBinding": { "elementId": "shape-id", "focus": 0, "gap": 1 },
  "points": [[0, 0], [200, 100]]
}
```

- `focus`: -1 to 1 — where on the shape edge the arrow connects
- `gap`: pixel distance from shape border

#### Text Inside Shapes

Create a shape, then a text element with `containerId` pointing to the shape's `id`:

```json
{"id": "box1", "type": "rectangle", "x": 100, "y": 100, "width": 200, "height": 80, ...}
{"type": "text", "text": "Crawler", "containerId": "box1", "textAlign": "center", "verticalAlign": "middle", ...}
```

#### Color Conventions

| Color | Hex | Use |
|-------|-----|-----|
| Default (black) | `#1e1e1e` | Existing elements |
| Green | `#2f9e44` | New or changed elements |
| Blue | `#1971c2` | Infrastructure components |
| Orange | `#e8590c` | External dependencies |

#### Stroke Styles

| Style | Value | Use |
|-------|-------|-----|
| Solid | `"solid"` | Existing connections |
| Dashed | `"dashed"` | New/proposed connections |
| Dotted | `"dotted"` | Optional/conditional flows |

#### Updating Existing Diagrams

When modifying an existing diagram:
1. Keep all original elements unchanged (same IDs, positions, colors)
2. Add new elements with `strokeColor: "#2f9e44"` (green)
3. Use `strokeStyle: "dashed"` for new arrows
4. Add annotation text elements near changes explaining what's new
5. Output the complete JSON (original + new elements) so it's a drop-in replacement

### Queue Message Contracts

```
frontier queue:
  FrontierItem { url, depth, priority, source_url?, domain, needs_puppeteer }
  Producer: Parser Service (new URLs), Seed loader
  Consumer: Crawler Service

parsing queue:
  ParsingQueueItem { url, minio_path, depth, domain }
  Producer: Crawler Service
  Consumer: Parser Service

extraction queue:
  ExtractionQueueItem { url, minio_path, text_content, page_title, domain }
  Producer: Parser Service (relevant pages only)
  Consumer: Extractor Service
```

### Generating the Dependency Map

```bash
python .claude/skills/cartographer/scripts/map_dependencies.py services/ --package shared --format mermaid
```

### Contributor Guide

Read `references/contributor_guide_template.md` for dev setup, service architecture,
how to add a new bank target, and the PR process.

## Workflow

When asked to map, document, or diagram:

1. **Determine scope** — whole system, single service, data flow, or specific feature?
2. **Read the actual code** — check docker-compose.yml, service entry points, shared models.
3. **Choose the right format**:
   - Quick inline diagram → Mermaid
   - Detailed architecture / annotating changes → Excalidraw JSON
4. **Produce the artifact** — output clipboard-pasteable Excalidraw JSON or Mermaid block.
5. **For Excalidraw updates** — include ALL original elements plus new ones in green.
6. **Verify accuracy** — cross-check against docker-compose.yml and actual imports.
