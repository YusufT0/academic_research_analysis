# 📚 Yapay Zeka Destekli Bilimsel Dergilerin Trend Analiz Sistemi

**BM495-BM496 Bilgisayar Mühendisliği Projesi I-II - 2025-2026 Güz-Bahar**

Bu proje, IEEE Xplore ve ScienceDirect gibi akademik platformlardan bilimsel makale meta-verilerini toplayan ve trend analizi için görselleştiren bir sistemdir.

## 👥 Ekip

| İsim | Numara |
|------|--------|
| Emre Faruk Küçük | 22118080039 |
| Yusuf Taha Sarıtiken | 22118080058 |
| Ali Burak Pekışık | 22118080062 |

---

## 🛠️ Teknolojiler

### Backend
- **Python 3.11+** - Ana programlama dili
- **FastAPI** - REST API framework
- **MongoDB** - NoSQL veritabanı
- **Beanie** - MongoDB ODM
- **Selenium** - Web scraping

### Frontend
- **Next.js 15** - React framework
- **TypeScript** - Type-safe JavaScript
- **Tailwind CSS** - Styling
- **Lucide React** - İkonlar

### Altyapı
- **Docker** - MongoDB containerization
- **Mongo Express** - MongoDB web UI

---

## 📋 Gereksinimler

Projeyi çalıştırmak için aşağıdaki yazılımların yüklü olması gerekir:

| Yazılım | Versiyon | İndirme |
|---------|----------|---------|
| Python | 3.11+ | https://python.org |
| Node.js | 20+ LTS | https://nodejs.org |
| Docker Desktop | Latest | https://docker.com |
| Git | Latest | https://git-scm.com |
| Google Chrome | Latest | (Scraper için) |

---

## 🚀 Kurulum

### 1. Repoyu Klonla
```bash
git clone https://github.com/emrefkucuk/academic_research_analysis.git
cd academic_research_analysis
```

### 2. MongoDB'yi Başlat (Docker)
```bash
cd scrapers
docker-compose up -d
```

Bu komut şunları başlatır:
- **MongoDB** → `localhost:27017`
- **Mongo Express** → `http://localhost:8081` (user: `admin`, pass: `admin123`)

### 3. Python Bağımlılıklarını Yükle
```bash
cd scrapers
pip install -r requirements.txt
```

### 4. Backend .env Dosyasını Oluştur
`scrapers/.env` dosyası oluştur:

```env
# MongoDB
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=academic_research

# Scraper Ayarları
AUTO_START_SCRAPERS=false
SCRAPER_HEADLESS=true
SCRAPER_RUN_MODE=parallel

# Makale Limitleri
IEEE_MAX_ARTICLES=10
SCIENCEDIRECT_MAX_ARTICLES=5
```

### 5. Frontend Bağımlılıklarını Yükle
```bash
cd client
npm install
npm install lucide-react recharts
```

### 6. Frontend .env Dosyasını Oluştur
`client/.env.local` dosyası oluştur:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

---

## ▶️ Çalıştırma

### Terminal 1: MongoDB (Docker çalışıyor olmalı)
```bash
cd scrapers
docker-compose up -d
```

### Terminal 2: Backend
```bash
cd scrapers
python run_backend.py
```
Backend başladığında:
- API: http://localhost:8000
- Swagger Docs: http://localhost:8000/docs

### Terminal 3: Frontend
```bash
cd client
npm run dev
```
Frontend başladığında:
- Web UI: http://localhost:3000

---

## 🌐 Servis Adresleri

| Servis | URL | Açıklama |
|--------|-----|----------|
| Frontend | http://localhost:3000 | Next.js Web UI |
| Backend API | http://localhost:8000 | FastAPI REST API |
| API Docs | http://localhost:8000/docs | Swagger Documentation |
| MongoDB | localhost:27017 | Database |
| Mongo Express | http://localhost:8081 | Database Web UI |

---

## 📁 Proje Yapısı

```
academic_research_analysis/
│
├── client/                          # Frontend (Next.js)
│   ├── app/                         # Sayfalar
│   │   ├── page.tsx                 # Dashboard
│   │   ├── articles/                # Makaleler listesi
│   │   ├── journals/                # Dergiler listesi
│   │   ├── search/                  # Arama sayfası
│   │   ├── trends/                  # Trend analizi
│   │   └── scrapers/                # Scraper kontrol
│   ├── components/                  # React componentleri
│   │   ├── dashboard/               # Dashboard componentleri
│   │   ├── layout/                  # Layout (Sidebar)
│   │   └── ui/                      # UI componentleri
│   └── lib/                         # API client & types
│
└── scrapers/                        # Backend (Python)
    ├── backend/                     # FastAPI API
    │   ├── core/                    # Config & dependencies
    │   ├── routers/                 # API endpoints
    │   ├── schemas/                 # Pydantic schemas
    │   └── services/                # Business logic
    ├── database/                    # MongoDB
    │   ├── models/                  # Beanie models
    │   └── repositories/            # Data access
    ├── ieee_xplore/                 # IEEE scraper
    ├── science_direct/              # ScienceDirect scraper
    ├── utils/                       # Utilities
    ├── docker/                      # Docker configs
    ├── docker-compose.yml
    ├── requirements.txt
    └── run_backend.py               # Başlatma scripti
```

---

## 🔌 API Endpoints

### Stats
| Method | Endpoint | Açıklama |
|--------|----------|----------|
| GET | `/api/v1/stats` | Genel istatistikler |
| GET | `/api/v1/stats/articles` | Makale istatistikleri |
| GET | `/api/v1/stats/scraper` | Scraper durumu |

### Journals
| Method | Endpoint | Açıklama |
|--------|----------|----------|
| GET | `/api/v1/journals` | Dergi listesi |
| GET | `/api/v1/journals/{id}` | Dergi detayı |
| GET | `/api/v1/journals/{id}/issues` | Derginin sayıları |
| GET | `/api/v1/journals/{id}/articles` | Derginin makaleleri |

### Articles
| Method | Endpoint | Açıklama |
|--------|----------|----------|
| GET | `/api/v1/articles` | Makale listesi |
| GET | `/api/v1/articles/{id}` | Makale detayı |
| GET | `/api/v1/articles/search?q=...` | Makale arama |

### Scrapers
| Method | Endpoint | Açıklama |
|--------|----------|----------|
| GET | `/api/v1/scrapers/status` | Tüm scraper durumu |
| POST | `/api/v1/scrapers/ieee/start` | IEEE scraper başlat |
| POST | `/api/v1/scrapers/ieee/stop` | IEEE scraper durdur |
| POST | `/api/v1/scrapers/sciencedirect/start` | ScienceDirect başlat |
| POST | `/api/v1/scrapers/sciencedirect/stop` | ScienceDirect durdur |
| POST | `/api/v1/scrapers/start-all` | Tümünü başlat |
| POST | `/api/v1/scrapers/stop-all` | Tümünü durdur |

---

## ⚙️ Environment Variables

### Backend (`scrapers/.env`)

```env
# ==========================================
# APP SETTINGS
# ==========================================
APP_NAME=Academic Research Scraper API
APP_VERSION=1.0.0
APP_DESCRIPTION="IEEE Xplore, ScienceDirect ve ACM'den akademik makale toplayan scraper'ları yönetir."

# Proxy Configuration
USE_PROXY=True
proxy_user=
proxy_pass=
proxy_host=proxy2.gazi.edu.tr
proxy_port=2001

# Science Direct URL
SCIENCEDIRECT_BASE_URL=https://www.sciencedirect.com/browse/journals-and-books?contentType=JL&subject=computer-science
IEEEXPLORE_BASE_URL=https://ieeexplore.ieee.org/browse/periodicals/title?contentType=periodicals&showActiveTitlesOnly=true&refinements=ContentType:Journals&rowsPerPage=100&pageNumber=1
ACM_BASE_URL=https://dl.acm.org/journals

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
RUN_TESTS_ON_STARTUP=false
AUTO_START_SCRAPERS=true
SCRAPER_HEADLESS=false
IEEE_MAX_ARTICLES=100
SCIENCEDIRECT_MAX_ARTICLES=100
ACM_MAX_ARTICLES=100

# Enabled Scrapers (comma separated: ieee,sciencedirect,acm)
# ieee: Sadece IEEE Xplore scraper çalışır
# sciencedirect: Sadece ScienceDirect scraper çalışır
# acm: Sadece ACM Digital Library scraper çalışır
# ieee,sciencedirect,acm: Tüm scraper'lar çalışır
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
NLP_MODEL_PATH=analyzer/clustering_model_.pkl
NLP_MODEL_VERSION=v1.0
NLP_EMBEDDER_MODEL=all-MiniLM-L6-v2
NLP_UMAP_N_NEIGHBORS=15
NLP_UMAP_N_COMPONENTS=10
NLP_MIN_CLUSTER_SIZE=20
NLP_MIN_SAMPLES=1
# NLP modelleri başlangıçta değil ilk kullanımda yüklensin mi
NLP_LAZY_INIT=true

# Redis Cache Settings
REDIS_ENABLED=true
REDIS_URL=redis://localhost:6440/0
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

# ==================== Elasticsearch ====================
ELASTICSEARCH_AUTO_SYNC=false
ELASTICSEARCH_URL=http://localhost:9200
ELASTICSEARCH_INDEX_PREFIX=academic

# ==================== API / Backend Settings ====================
DEBUG=false
CORS_ORIGINS=["*"]
LOG_FORMAT=pretty

# ==================== Scraper Wait Settings ====================
IEEE_MIN_WAIT=4
IEEE_MAX_WAIT=10
IEEE_PAGE_LOAD_TIMEOUT=90
SD_TIMEOUT=90
SD_IMPLICIT_WAIT=90
ACM_MIN_WAIT=4
ACM_MAX_WAIT=10
ACM_PAGE_LOAD_TIMEOUT=90

# ==================== PDF Download Settings ====================
PDF_DOWNLOAD_TIMEOUT=60
PDF_DOWNLOAD_CHUNK_SIZE=8192

# ==================== Redis Streams ====================
REDIS_STREAMS_ENABLED=true
REDIS_STREAMS_CONSUMER_GROUP=academic-backend
REDIS_STREAMS_DLQ_RETRY_INTERVAL=300
```

### Frontend (`client/.env.local`)

```env
# Backend API URL
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

---

## 🔧 Sorun Giderme

### MongoDB bağlantı hatası
```bash
# Docker'ın çalıştığından emin ol
docker ps

# Container'ları yeniden başlat
cd scrapers
docker-compose down
docker-compose up -d
```

### Scraper modülü yüklenemedi hatası
```bash
# distutils hatası için (Python 3.12+)
pip install setuptools
```

### Frontend CORS hatası
Backend'in CORS ayarları `scrapers/backend/core/config.py` dosyasında. Varsayılan olarak tüm originlere izin verir.

### PowerShell script execution hatası
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

## 📝 Lisans

Bu proje Gazi Üniversitesi Bilgisayar Mühendisliği Bölümü BM495-BM496 dersleri kapsamında geliştirilmiştir.

---

## 📧 İletişim

Sorularınız için: [GitHub Issues](https://github.com/emrefkucuk/academic_research_analysis/issues)

