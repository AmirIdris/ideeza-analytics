# IDEEZA Analytics API

Senior Backend Developer Assessment - Django Analytics API with PostgreSQL and Redis.

---

## ⚠️ IMPORTANT: Database Reset Required

**The database schema has been updated.** If you have an existing database, you **MUST** reset it first:

```bash
docker-compose down -v
```

This will drop all volumes (including the database). Then proceed with the Quick Start steps below.

---

## Quick Start

```bash
# 1. Start containers
docker-compose up -d --build

# 2. Apply migrations
docker-compose exec web python manage.py migrate

# 3. Generate test data (10,000+ records)
docker-compose exec web python manage.py seed_data

# 4. Pre-calculate analytics summaries (REQUIRED for fast API)
docker-compose exec web python manage.py precalculate_stats
```

**Access:**
- Swagger: http://localhost:8000/swagger/
- Admin: http://localhost:8000/admin/

---

## API Endpoints

### 1. Grouped Analytics
`POST /api/analytics/blog-views/{country|user}/`

> **⚠️ IMPORTANT:** This endpoint uses pre-calculated data. You **MUST** run `precalculate_stats` first, otherwise it will return empty results.

```bash
curl -X POST http://localhost:8000/api/analytics/blog-views/country/ \
  -H "Content-Type: application/json" \
  -d '{"year": 2025}'
```

**Response:** `x` = grouping key, `y` = unique blogs, `z` = total views
```json
[{"x": "US", "y": 25, "z": 5432}, {"x": "UK", "y": 18, "z": 3210}]
```

### 2. Top 10
`POST /api/analytics/top/{blog|user|country}/`

```bash
curl -X POST http://localhost:8000/api/analytics/top/blog/ \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Response:** `x` = name, `y` = total views, `z` = unique count
```json
[{"x": "Best Blog", "y": 1234, "z": 15}]
```

### 3. Performance
`POST /api/analytics/performance/`

```bash
curl -X POST http://localhost:8000/api/analytics/performance/ \
  -H "Content-Type: application/json" \
  -d '{"year": 2025}'
```

**Response:** `x` = date + blogs, `y` = views, `z` = growth %
```json
[{"x": "2025-01-01 (15 blogs)", "y": 1234, "z": 0.0}, {"x": "2025-01-08 (18 blogs)", "y": 1456, "z": 17.99}]
```

---

## Filter Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `range` | string | `day`, `week`, `month`, `year` |
| `year` | int | Filter by year |
| `country_codes` | list | Include countries (OR logic) |
| `exclude_country_codes` | list | Exclude countries (NOT logic) |
| `author_username` | string | Filter by author |

**Example - Combined filters:**
```json
{
  "year": 2025,
  "country_codes": ["US", "UK"],
  "exclude_country_codes": ["SPAM"]
}
```

---

## Design Approach

### The Problem
Analytics queries on 10,000+ raw events are expensive and require complex filtering.

### The Solution
**Pre-calculate daily summaries** → Query ~365 rows instead of 10,000.

**API #1 uses the fast pre-calculated approach.** You **MUST** run precalc before testing:

```bash
docker-compose exec web python manage.py precalculate_stats
```

| Approach | Query Time | Use Case |
|----------|------------|----------|
| Pre-calculated (API #1) | ~5-10ms | **Current implementation** |
| Real-time (not used) | ~50-200ms | Would require code changes |

### How Pre-Calculation Works

**Implementation:**
1. **New Table: `DailyAnalyticsSummary`**
   - Stores pre-aggregated daily statistics
   - Columns: `date`, `country`, `author`, `total_views`, `unique_blogs`
   - One row per day/country/author combination

2. **Pre-Calculation Process:**
   - Management command aggregates `BlogView` events by day
   - Calculates totals once (offline), not on every API call
   - Runs via: `python manage.py precalculate_stats`

3. **Query Simplification:**
   - **Before:** Complex filtering on 10,000+ raw events with multiple WHERE clauses
   - **After:** Simple SUM aggregation on ~365 pre-calculated rows
   - Uses declarative Q objects instead of complex conditional filtering

**What Problem It Solves:**
- ❌ **Eliminates complex filtering** - No need for complex WHERE clauses on raw events
- ❌ **Eliminates expensive calculations** - Aggregations done once, not per-request
- ❌ **Eliminates N+1 queries** - Pre-calculated data is already joined
- ✅ **Simple queries** - Just SUM the pre-calculated values
- ✅ **Fast responses** - Query ~365 rows instead of 10,000+ events
- ✅ **Scalable** - Performance doesn't degrade as event count grows

**The `DailyAnalyticsSummary` Table:**
- **Purpose:** Store pre-calculated daily aggregates to avoid real-time computation
- **Structure:** One row = one day's stats for one country + one author
- **Example:** 1 year of data = ~365 rows (vs 10,000+ raw events)
- **Indexes:** Optimized for date/country and date/author lookups
- **Updates:** Refreshed daily via scheduled job (not real-time)

**Note:** For this assessment, a simple management command (`precalculate_stats`) is used for simplicity. In production, this would be automated via Celery Beat or cron.


---

## Architecture

- **Models:** `BlogView` (fact table) + `DailyAnalyticsSummary` (pre-calculated)
- **Optimization:** Composite indexes, `select_related()`, Redis caching (15 min)
- **Security:** JWT authentication, typed serializers

---

## Commands

| Action | Docker Command | Makefile (optional) |
|--------|----------------|---------------------|
| Start | `docker-compose up -d --build` | `make up` |
| Migrate | `docker-compose exec web python manage.py migrate` | `make migrate` |
| Seed data | `docker-compose exec web python manage.py seed_data` | `make seed` |
| Pre-calculate | `docker-compose exec web python manage.py precalculate_stats` | `make precalc` |
| Run tests | `docker-compose exec web python manage.py test` | `make test` |
| View logs | `docker-compose logs -f` | `make logs` |
| Stop | `docker-compose down` | `make down` |

---

## Tech Stack

- Python 3.11 / Django 4.2 / DRF
- PostgreSQL 15 / Redis 7
- Docker / Swagger (drf-yasg)
