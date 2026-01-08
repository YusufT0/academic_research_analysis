# Kurulum ve Çalıştırma

## Gereksinimler

| Yazılım | Minimum Versiyon |
|---------|------------------|
| Python | 3.11+ |
| Node.js | 20+ LTS |
| Docker Desktop | Latest |
| Google Chrome | Latest |

## Kurulum

### 1. Docker Servislerini Başlat

```bash
cd scrapers
docker-compose up -d
```

Bu komut MongoDB, Redis ve web arayüzlerini başlatır:
- MongoDB: `localhost:27017`
- Redis: `localhost:6379`
- Mongo Express: `http://localhost:8081` (admin/admin123)
- Redis Commander: `http://localhost:8082`

### 2. Backend Kurulumu

```bash
cd scrapers
pip install -r requirements.txt
```

`scrapers/.env` dosyası oluştur:

```
# Proxy Configuration
USE_PROXY=True
proxy_user=
proxy_pass=
proxy_host=proxy2.gazi.edu.tr
proxy_port=2001

# Science Direct URL
SCIENCEDIRECT_BASE_URL=https://www.sciencedirect.com/browse/journals-and-books?contentType=JL&subject=computer-science
IEEEXPLORE_BASE_URL=https://ieeexplore.ieee.org/browse/periodicals/title?contentType=periodicals&showActiveTitlesOnly=true&refinements=ContentType:Journals&rowsPerPage=100&pageNumber=1

# MongoDB Configuration
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=academic_research

# MongoDB Authentication (optional - for production)
MONGODB_USERNAME=
MONGODB_PASSWORD=

# MongoDB Connection Settings
MONGODB_MIN_POOL_SIZE=1
MONGODB_MAX_POOL_SIZE=10

# Scraper Settings
SCRAPER_LOG_LEVEL=INFO
SCRAPER_LOG_FILE=logs/scraper.log

# Backend Settings
AUTO_START_SCRAPERS=false
SCRAPER_HEADLESS=false
IEEE_MAX_ARTICLES=100
SCIENCEDIRECT_MAX_ARTICLES=100

# Enabled Scrapers (comma separated: ieee,sciencedirect)
# ieee: Sadece IEEE Xplore scraper çalışır
# sciencedirect: Sadece ScienceDirect scraper çalışır
# ieee,sciencedirect: Her iki scraper da çalışır (varsayılan)
ENABLED_SCRAPERS=ieee,sciencedirect

# Scraper Run Mode
# parallel: Scraper'lar aynı anda çalışır (5 sn arayla başlar)
# sequential: Scraper'lar sırayla çalışır (biri bitince diğeri başlar)
# round_robin: Her 3 journalda bir diğer siteye geçilir (döngüsel: IEEE -> SD -> IEEE -> ...)
SCRAPER_RUN_MODE=round_robin

# Round Robin Settings (only for round_robin mode)
ROUND_ROBIN_JOURNALS_PER_SWITCH=1

# NLP/Clustering Settings
# true: Önce PKL dosyasını kullan, yoksa DB'ye bak
# false: Önce DB'ye bak, yoksa PKL'yi dene
NLP_PREFER_PKL=true

# NLP/Clustering Settings
NLP_MODEL_PATH=analyzer/clustering_model_.pkl
NLP_MODEL_VERSION=v1.0
NLP_EMBEDDER_MODEL=all-MiniLM-L6-v2
NLP_UMAP_N_NEIGHBORS=15
NLP_UMAP_N_COMPONENTS=10
NLP_MIN_CLUSTER_SIZE=20

# Redis Cache Settings
REDIS_ENABLED=true
REDIS_URL=redis://localhost:6379/0
REDIS_PREFIX=academic

# Cache TTL Settings (saniye)
CACHE_TTL_ARTICLE=3600
CACHE_TTL_JOURNAL=21600
CACHE_TTL_ISSUE=7200
CACHE_TTL_CLUSTER=1800
CACHE_TTL_SEARCH=900
CACHE_TTL_STATS=300

# Prefetch Settings
PREFETCH_ENABLED=true
PREFETCH_ARTICLES_PER_ISSUE=20
PREFETCH_ISSUES_PER_JOURNAL=3
PREFETCH_ARTICLES_PER_CLUSTER=50
PREFETCH_NEIGHBOR_CLUSTERS=1
PREFETCH_NEIGHBOR_ISSUES=1
PREFETCH_NEIGHBOR_ARTICLES_LIMIT=20
NLP_MIN_SAMPLES=1
```

### 3. Frontend Kurulumu

```bash
cd client
npm install
```

`client/.env.local` dosyası oluştur:

```
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

## Çalıştırma

### Backend

```bash
cd scrapers
python run_backend.py
```

- API: http://localhost:8000
- Swagger Docs: http://localhost:8000/docs

### Frontend

```bash
cd client
npm run dev
```

- Web UI: http://localhost:3000

## Servis Adresleri

| Servis | URL |
|--------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| MongoDB | localhost:27017 |
| Mongo Express | http://localhost:8081 |
| Redis | localhost:6379 |
| Redis Commander | http://localhost:8082 |