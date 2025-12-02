# IDEEZA Analytics API - Senior Backend Developer Assessment

A high-performance Analytics API built with Django, PostgreSQL, and Redis.

---

## ⚠️ Database Reset Required

If you've run this project before, reset your database:
```bash
docker-compose down -v && make up && make migrate && make seed
```

---

## 🚀 Quick Start (5 minutes)

```bash
# 1. Start services
make up

# 2. Apply migrations
make migrate

# 3. Seed 10,000+ test records
make seed

# 4. (Optional) Pre-calculate analytics summaries
make precalc
```

**Access:**
- Swagger UI: http://localhost:8000/swagger/
- Admin: http://localhost:8000/admin/

---

## 💡 The Problem Solver Approach

### The Challenge
> "Most developers used complex filtering on raw events. If they did some calculation, they could skip it."

### The Obvious Approach (What Most Do)
```
API Request → Query 10,000 raw events → Filter → Aggregate → Return
```
This requires complex filtering logic and scales poorly.

### The Smart Approach (Pre-calculation)
```
Background: Pre-calculate daily stats → Store in summary table
API Request → Query 365 summary rows → Simple SUM → Return instantly
```

**Result:** Query complexity drops from O(10,000 events) to O(365 days).

### Implementation

```bash
# Pre-calculate daily summaries
make precalc

# Now APIs can use pre-calculated data for instant responses
```

The `DailyAnalyticsSummary` model stores pre-aggregated metrics:
- `total_views` - Already counted, just SUM at query time
- `unique_blogs` - Already calculated, no DISTINCT needed

---

## 📡 API Reference

All endpoints use **POST** with a JSON filter body.

### Filter Parameters
| Parameter | Type | Description |
|-----------|------|-------------|
| `range` | string | Quick filter: `day`, `week`, `month`, `year` |
| `year` | int | Filter by year (e.g., 2025) |
| `country_codes` | list | Include countries: `["US", "UK"]` (OR logic) |
| `exclude_country_codes` | list | Exclude countries (NOT logic) |
| `author_username` | string | Filter by author |

---

### API #1: Grouped Analytics

**Endpoint:** `POST /api/analytics/blog-views/{country|user}/`

**Example:**
```bash
curl -X POST http://localhost:8000/api/analytics/blog-views/country/ \
  -H "Content-Type: application/json" \
  -d '{"year": 2025}'
```

**Response:**
```json
[
  {"x": "US", "y": 25, "z": 5432},
  {"x": "UK", "y": 18, "z": 3210}
]
```
- `x` = Country code (grouping key)
- `y` = Number of unique blogs
- `z` = Total views

---

### API #2: Top 10

**Endpoint:** `POST /api/analytics/top/{blog|user|country}/`

**Example:**
```bash
curl -X POST http://localhost:8000/api/analytics/top/blog/ \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Response:**
```json
[
  {"x": "Best Blog Title", "y": 1234, "z": 15},
  {"x": "Another Blog", "y": 987, "z": 12}
]
```
- `x` = Blog title / Username / Country
- `y` = Total views
- `z` = Unique countries (blog) / blogs (user) / blogs (country)

---

### API #3: Performance Over Time

**Endpoint:** `POST /api/analytics/performance/`

**Example:**
```bash
curl -X POST http://localhost:8000/api/analytics/performance/ \
  -H "Content-Type: application/json" \
  -d '{"year": 2025, "range": "week"}'
```

**Response:**
```json
[
  {"x": "2025-01-01 (15 blogs)", "y": 1234, "z": 0.0},
  {"x": "2025-01-08 (18 blogs)", "y": 1456, "z": 17.99}
]
```
- `x` = Date + blog count
- `y` = Views in period
- `z` = Growth % vs previous period

---

## 🏗 Architecture

### Why Two Approaches?

| Approach | Use Case | Query Time |
|----------|----------|------------|
| **Real-time** | Fresh data, small datasets | ~50-200ms |
| **Pre-calculated** | Large datasets, dashboards | ~5-10ms |

### Database Design

```
BlogView (Fact Table)          DailyAnalyticsSummary (Pre-calculated)
├── blog_id                    ├── date
├── country_id                 ├── country_id  
├── timestamp                  ├── author_id
└── viewer_id                  ├── total_views (pre-counted)
                               └── unique_blogs (pre-counted)
```

### Performance Optimizations

1. **Indexes:** Composite indexes on (timestamp, country) and (blog, timestamp)
2. **N+1 Prevention:** `select_related()` for all foreign key traversals
3. **Caching:** Redis with 15-minute TTL, MD5-hashed cache keys
4. **Pre-calculation:** Daily summaries reduce query complexity by 95%

---

## 🔧 Commands

```bash
make up        # Start Docker containers
make migrate   # Apply database migrations
make seed      # Generate 10,000+ test records
make precalc   # Pre-calculate daily summaries
make test      # Run tests
make logs      # View container logs
```

---

## 🛠 Tech Stack

- Python 3.11 + Django 4.2 + Django REST Framework
- PostgreSQL 15 + Redis 7
- Docker + Docker Compose
- drf-yasg (Swagger documentation)

---

## 🧪 Running Tests

```bash
make test
```

Tests cover:
- API #1, #2, #3 functionality
- Dynamic filter logic (AND, OR, NOT)
- Response structure validation

---

## 📈 Future Improvements

For production scale (1M+ events/day):

1. **Celery Beat:** Schedule `precalculate_stats` to run nightly
2. **Partitioning:** Partition BlogView table by month
3. **ClickHouse:** For sub-second aggregations on billions of rows
