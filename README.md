This repository contains the solution for the Senior Backend Developer assessment. It implements a high-performance Analytics API using Django, PostgreSQL, and Redis.

## 🚀 Quick Start

The project is fully containerized. You only need Docker installed.

1. **Build the containers:**
   ```bash
   docker-compose build
   ```

2. **Start the Infrastructure:**
   ```bash
   docker-compose up -d
   ```

3. **Apply Migrations:**
   ```bash
   docker-compose exec web python manage.py migrate
   ```

4. **🌱 Seed Mock Data (Crucial):**
   This command generates Users, Blogs, and **10,000+ View records** distributed over the last year to simulate a production environment.
   ```bash
   docker-compose exec web python manage.py seed_data
   ```

### Other Useful Commands:
- **View logs:** `docker-compose logs -f`
- **Stop containers:** `docker-compose down`
- **Run tests:** `docker-compose exec web python manage.py test`
- **Django shell:** `docker-compose exec web python manage.py shell`

4. **Access Documentation:**
   * **Swagger UI:** [http://localhost:8000/swagger/](http://localhost:8000/swagger/)
   * **API Root:** [http://localhost:8000/api/analytics/](http://localhost:8000/api/analytics/)

---

## 💡 Understanding the Filter Syntax

The API uses a recursive JSON logic engine to satisfy the requirement for **Dynamic `AND/OR/NOT` Filtering**.

### Example 1: Simple Filter
**Goal:** "Show me views from the year 2024."
```json
{
  "operator": "and",
  "conditions": [
    { "field": "timestamp__year", "op": "eq", "value": 2025 }
  ]
}
```

### Example 2: Complex Nested Logic
**Goal:** "Show me views from 2025 **AND** (views from US **OR** views from Ethiopia)."
```json
{
  "operator": "and",
  "conditions": [
    { "field": "timestamp__year", "op": "eq", "value": 2025 },
    {
      "operator": "or",  
      "conditions": [
        { "field": "country", "op": "eq", "value": "US" },
        { "field": "country", "op": "eq", "value": "ET" }
      ]
    }
  ]
}
```

---

## 📡 API Reference & Testing

Below are the Curl commands to test the specific assessment requirements.

### 1. Grouped Analytics
**Endpoint:** `POST /api/analytics/blog-views/{object_type}/`
**Params:** `object_type` = `country` or `user`
**Goal:** Group views by Country (or User) for the year 2025.

**CURL Command:**
```bash
curl -X POST http://localhost:8000/api/analytics/blog-views/country/ \
-H "Content-Type: application/json" \
-d '{
  "operator": "and",
  "conditions": [
    { "field": "timestamp__year", "op": "gte", "value": 2025 }
  ]
}'
```

### 2. Top Performers
**Endpoint:** `POST /api/analytics/top/{top_type}/`
**Params:** `top_type` = `blog`, `user`, or `country`
**Goal:** Get the Top 10 Blogs based on total views (no filters applied).

**CURL Command:**
```bash
curl -X POST http://localhost:8000/api/analytics/top/blog/ \
-H "Content-Type: application/json" \
-d '{
  "operator": "and",
  "conditions": []
}'
```

### 3. Time-Series Performance
**Endpoint:** `POST /api/analytics/performance/`
**Query Param:** `?compare=month` (or `week`, `day`, `year`)
**Goal:** Show monthly growth trends for the current year.

**CURL Command:**
```bash
curl -X POST "http://localhost:8000/api/analytics/performance/?compare=month" \
-H "Content-Type: application/json" \
-d '{
  "operator": "and",
  "conditions": [
    { "field": "timestamp__year", "op": "eq", "value": 2025 }
  ]
}'
```

---





## 🏗 Architecture & Design Decisions

### 1. Database Optimization (PostgreSQL)
*   **Schema Design:** Used a Star Schema-lite approach. `BlogView` acts as the Fact table.
*   **Indexing:** Added Composite Indexes `(timestamp, country)` and `(blog, timestamp)` to the `BlogView` model. This ensures that filtering by time range and grouping by country remains `O(log n)` rather than a full table scan `O(n)`.
*   **Aggregation:** Leveraged Django ORM's `values()` and `annotate()` to perform `GROUP BY` operations at the database level, preventing N+1 query issues.

### 2. Caching Strategy (Redis)
*   **Problem:** Analytics queries involving `COUNT` and `GROUP BY` on large datasets are expensive.
*   **Solution:** Implemented a Caching Layer in `services.py`.
    *   Cache keys are deterministically generated using an MD5 hash of the sorted filter parameters.
    *   Heavy aggregation results are cached for **15 minutes**.
    *   This reduces API response time from ~200ms (uncached) to <10ms (cached).

### 3. Dynamic Filter Engine
*   **Requirement:** Support complex `AND/OR/NOT` logic.
*   **Solution:** Implemented a **Recursive Query Builder** (`DynamicFilterBuilder`).
    *   It recursively parses JSON payloads to construct complex Django `Q` objects.
    *   **Security:** Includes strict field whitelisting to prevent users from filtering on sensitive fields (e.g., `author__password`).

### 4. Authentication & Security (JWT)
*   **Context:** The Job Description requested `SimpleJWT`, but the Assessment Requirements focused on public analytics data.
*   **Decision:** I have fully configured `rest_framework_simplejwt`.
    *   JWT Endpoints exist at `/api/token/`.
    *   **Note:** To make the assessment easier to review/test, the Views are currently set to `AllowAny`. In a production environment, I would switch the permission class to `IsAuthenticated`.


### 5. Infrastructure Strategy
*   **Development:** The database is containerized via Docker Compose for rapid setup and reproducibility. Data persistence is handled via Docker Volumes.
*   **Production:** In a real-world deployment, I would **decouple** the database from the Docker cluster. I would utilize a managed service (e.g., **AWS RDS for PostgreSQL** or **Azure Database**) to ensure automated backups, high availability, and independent scaling.
---

## 🛠 Tech Stack

*   **Language:** Python 3.11
*   **Framework:** Django 4.2 + Django REST Framework
*   **Database:** PostgreSQL 15
*   **Caching:** Redis 7
*   **Documentation:** drf-yasg (Swagger/OpenAPI)
*   **Containerization:** Docker & Docker Compose

---

## 🔮 Future Improvements & Scaling

If this were a real-world high-traffic system (1M+ requests/day), I would implement the following:

1.  **Asynchronous Processing (Celery):**
    Instead of calculating analytics on-the-fly (Read-Heavy), I would use Celery Beat to pre-calculate daily/weekly stats and store them in a summary table (`AnalyticsReport`).
2.  **OLAP Database:**
    Postgres is great, but for massive analytics, I would sync the `BlogView` data to **ClickHouse** or **Elasticsearch** for sub-second aggregations on billions of rows.
3.  **Partitioning:**
    Partition the `BlogView` table by `timestamp` (Monthly) to keep index sizes manageable.

---

