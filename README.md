# AI-Powered Trend Analysis System for Scientific Journals

**BM495-BM496 Computer Engineering Project I-II - 2025-2026 Fall-Spring**
**Gazi University - Faculty of Engineering - Department of Computer Engineering**

A system that collects scientific article metadata from IEEE Xplore, ScienceDirect and the ACM Digital Library, performs topic clustering and similarity analysis with NLP/AI, and visualizes the results through interactive charts.

## Team

| Name | Student ID |
|------|------------|
| Emre Faruk Kucuk | 22118080039 |
| Yusuf Taha Saritiken | 22118080058 |
| Ali Burak Pekisik | 22118080062 |

---

## Technologies

### Backend
- **Python 3.11+** - Main programming language
- **FastAPI** - REST API framework
- **MongoDB + Beanie** - NoSQL database and ODM
- **Redis** - Cache, WebSocket Pub/Sub, Streams
- **Elasticsearch 8** - Full-text search and autocomplete
- **Selenium / SeleniumBase** - Web scraping

### NLP / AI
- **SentenceTransformers** - Article embedding generation
- **UMAP** - Dimensionality reduction
- **HDBSCAN** - Topic clustering
- **KeyBERT** - Keyword extraction
- **spaCy** - Natural language processing

### Frontend
- **Next.js 15** - React framework (App Router)
- **TypeScript** - Type-safe JavaScript
- **Tailwind CSS v4** - Styling
- **Recharts** - Charting library
- **react-force-graph-2d** - Interactive citation map
- **Lucide React** - Icons

### Infrastructure & Monitoring
- **Docker Compose** - MongoDB, Redis, Elasticsearch, Prometheus, Grafana
- **Prometheus** - Metrics collection
- **Grafana** - Dashboards and visualization

---

## Requirements

| Software | Version | Download |
|----------|---------|----------|
| Python | 3.11+ | https://python.org |
| Node.js | 20+ LTS | https://nodejs.org |
| Docker Desktop | Latest | https://docker.com |
| Git | Latest | https://git-scm.com |
| Google Chrome | Latest | Required for the scrapers |

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/emrefkucuk/academic_research_analysis.git
cd academic_research_analysis
```

### 2. Start the Docker Services

```bash
cd scrapers
docker compose up -d
```

This command starts the following 7 services:

| Service | Port | Description |
|---------|------|-------------|
| MongoDB | 27017 | Database |
| Redis | 6440 | Cache & Streams |
| Elasticsearch | 9200 | Full-text search engine |
| Prometheus | 9090 | Metrics collection |
| Grafana | 3001 | Monitoring dashboards |
| Mongo Express | 8081 | MongoDB web UI |
| Redis Commander | 8082 | Redis web UI |

To make sure the services are ready:

```bash
docker compose ps
```

Wait until all services are in the `running` or `healthy` state. Elasticsearch may take ~60 seconds to start.

### 3. Install Python Dependencies

```bash
cd scrapers
pip install -r requirements.txt
```

> **Note:** Some NLP libraries (sentence-transformers, torch, etc.) can be large. The first installation downloads ~1-2 GB.

### 4. Create the Backend .env File

You can start by copying `scrapers/.env.example`:

```bash
cp .env.example .env
```

Or create `scrapers/.env` with the following minimum settings:

```env
# MongoDB
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=academic_research

# Redis
REDIS_ENABLED=true
REDIS_URL=redis://localhost:6440/0

# Elasticsearch
ELASTICSEARCH_URL=http://localhost:9200
ELASTICSEARCH_AUTO_SYNC=false

# Scraper Settings
AUTO_START_SCRAPERS=false
SCRAPER_HEADLESS=true

# NLP
NLP_LAZY_INIT=true
NLP_EMBEDDER_MODEL=all-MiniLM-L6-v2
```

See `.env.example` for all configuration options.

### 5. Install Frontend Dependencies

```bash
cd client
npm install
```

### 6. Frontend .env File

The `client/.env` file should already exist. If not, create it:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

---

## Running the Project

Running the project requires **3 separate terminals**:

### Terminal 1: Docker Services

```bash
cd scrapers
docker compose up -d
```

### Terminal 2: Python Backend

```bash
cd scrapers
python run_backend.py
```

On a successful start you will see the following output:

```
BACKEND HAZIR
API: http://localhost:8000
Docs: http://localhost:8000/docs
```

### Terminal 3: Next.js Frontend

**Development mode** (hot reload, page transitions are a bit slower):

```bash
cd client
npm run dev
```

**Production mode** (fast page transitions, no hot reload):

```bash
cd client
npm run build
npm start
```

Frontend address: http://localhost:3000

---

## Service Addresses

| Service | URL | Username / Password |
|---------|-----|---------------------|
| Frontend | http://localhost:3000 | - |
| Backend API | http://localhost:8000 | - |
| Swagger API Docs | http://localhost:8000/docs | - |
| Mongo Express | http://localhost:8081 | admin / admin123 |
| Redis Commander | http://localhost:8082 | - |
| Grafana | http://localhost:3001 | admin / admin123 |
| Prometheus | http://localhost:9090 | - |

---

## Important Usage Notes

### Data Collection (Scrapers)

The system starts with an empty database. To collect articles:

1. Go to the **Scraper** page in the frontend
2. Start one of the IEEE, ScienceDirect or ACM scrapers
3. You can follow the scraper status live via WebSocket

### AI / NLP Analysis

The NLP module is **trained automatically on first use**:

1. Go to the **Search** page
2. Enter a keyword (for example "machine learning")
3. Click the **AI Analysis** button
4. If the model has not been trained yet, training starts automatically (30 s - 5 min)
5. When training finishes, the cluster information, 3 charts and matching articles are shown

> **Note:** Training requires at least ~20 articles with abstracts in the database. If there are not enough articles, run a scraper first.

### Citation Map

The **Citation Map** page shows citation relationships between articles as an interactive network graph. This feature requires citation data to have been fetched from OpenAlex.

---

## Project Structure

```
academic_research_analysis/
|
+-- client/                          # Frontend (Next.js 15)
|   +-- app/                         # Pages (App Router)
|   |   +-- page.tsx                 # Dashboard
|   |   +-- articles/                # Article list & detail
|   |   +-- journals/                # Journal list & detail
|   |   +-- authors/                 # Author profiles
|   |   +-- search/                  # Search + AI analysis
|   |   +-- trends/                  # Trend charts
|   |   +-- citation-map/            # Interactive citation map
|   |   +-- scrapers/                # Scraper control panel
|   +-- components/                  # React components
|   |   +-- dashboard/               # Dashboard components
|   |   +-- layout/                  # Sidebar navigation
|   |   +-- providers/               # WebSocket ScraperProvider
|   |   +-- ui/                      # Card, Badge, Button, Input
|   +-- lib/                         # API client, types, hooks
|
+-- scrapers/                        # Backend (Python)
    +-- backend/                     # FastAPI application
    |   +-- core/                    # Config & middleware
    |   +-- routers/                 # API endpoints
    |   +-- services/                # NLP, cache, scraper services
    |   +-- schemas/                 # Pydantic response models
    +-- database/                    # MongoDB
    |   +-- models/                  # Beanie ODM models
    |   +-- repositories/            # Data access layer
    +-- ieee_xplore/                 # IEEE Xplore scraper
    +-- science_direct/              # ScienceDirect scraper
    +-- acm/                         # ACM Digital Library scraper
    +-- docker/                      # Docker configurations
    |   +-- prometheus/              # Prometheus config
    |   +-- grafana/                 # Grafana dashboards & provisioning
    +-- tests/                       # pytest tests
    +-- utils/                       # Logger and helper modules
    +-- docker-compose.yml
    +-- requirements.txt
    +-- run_backend.py               # Backend startup script
```

---

## API Endpoints

See the Swagger UI for the full list: http://localhost:8000/docs

### Stats
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/stats` | General statistics |
| GET | `/api/v1/stats/articles` | Article statistics |
| GET | `/api/v1/stats/citations` | Citation statistics |

### Journals
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/journals` | Journal list (paginated, filterable) |
| GET | `/api/v1/journals/{id}` | Journal detail |
| GET | `/api/v1/journals/{id}/issues` | Issues of the journal |
| GET | `/api/v1/journals/{id}/articles` | Articles of the journal |
| GET | `/api/v1/journals/{id}/citation-metrics` | Journal citation metrics and historical chart |

### Articles
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/articles` | Article list (paginated, filterable) |
| GET | `/api/v1/articles/{id}` | Article detail |
| GET | `/api/v1/articles/{id}/citation-metrics` | Article citation metrics |

### Search
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/search?q=...` | Elasticsearch full-text search |
| GET | `/api/v1/search/suggest?q=...` | Autocomplete suggestions |
| GET | `/api/v1/search/facets` | Search facets (source, year, journal) |

### NLP / AI
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/nlp/status` | NLP model status |
| GET | `/api/v1/nlp/search?query=...` | Semantic similarity search |
| GET | `/api/v1/nlp/get_bar_chart_input` | Article distribution by year |
| GET | `/api/v1/nlp/get_pie_chart_input` | Topic distribution |
| GET | `/api/v1/nlp/get_scatter_chart_input` | 2D UMAP scatter data |
| POST | `/api/v1/nlp/train` | Manual model training |
| GET | `/api/v1/nlp/clusters` | List all clusters |

### Scrapers
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/scrapers/status` | Status of all scrapers |
| POST | `/api/v1/scrapers/ieee/start` | Start the IEEE scraper |
| POST | `/api/v1/scrapers/ieee/stop` | Stop the IEEE scraper |
| POST | `/api/v1/scrapers/sciencedirect/start` | Start ScienceDirect |
| POST | `/api/v1/scrapers/acm/start` | Start ACM |
| POST | `/api/v1/scrapers/start-all` | Start all |
| POST | `/api/v1/scrapers/stop-all` | Stop all |

### Authors & Citations
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/authors` | Author list |
| GET | `/api/v1/authors/{name}` | Author profile |
| GET | `/api/v1/citation-graph?article_id=...` | Citation graph data |

### WebSocket
| Endpoint | Description |
|----------|-------------|
| `ws://localhost:8000/ws/scrapers/events` | Live scraper event stream |
