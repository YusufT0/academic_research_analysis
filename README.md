# Yapay Zeka Destekli Bilimsel Dergilerin Trend Analiz Sistemi

**BM495-BM496 Bilgisayar Muhendisligi Projesi I-II - 2025-2026 Guz-Bahar**

IEEE Xplore, ScienceDirect ve ACM Digital Library platformlarindan bilimsel makale meta-verilerini toplayan, NLP/AI ile konu kumeleme ve benzerlik analizi yapan ve sonuclari interaktif grafiklerle gorselestiren bir sistemdir.

## Ekip

| Isim | Numara |
|------|--------|
| Emre Faruk Kucuk | 22118080039 |
| Yusuf Taha Saritiken | 22118080058 |
| Ali Burak Pekisik | 22118080062 |

---

## Teknolojiler

### Backend
- **Python 3.11+** - Ana programlama dili
- **FastAPI** - REST API framework
- **MongoDB + Beanie** - NoSQL veritabani ve ODM
- **Redis** - Cache, WebSocket Pub/Sub, Streams
- **Elasticsearch 8** - Full-text arama ve autocomplete
- **Selenium / SeleniumBase** - Web scraping

### NLP / AI
- **SentenceTransformers** - Makale embedding olusturma
- **UMAP** - Boyut indirgeme
- **HDBSCAN** - Konu kumeleme (clustering)
- **KeyBERT** - Anahtar kelime cikarma
- **spaCy** - Dogal dil isleme

### Frontend
- **Next.js 15** - React framework (App Router)
- **TypeScript** - Type-safe JavaScript
- **Tailwind CSS v4** - Styling
- **Recharts** - Grafik kutuphanesi
- **react-force-graph-2d** - Interaktif atif haritasi
- **Lucide React** - Ikonlar

### Altyapi & Monitoring
- **Docker Compose** - MongoDB, Redis, Elasticsearch, Prometheus, Grafana
- **Prometheus** - Metrik toplama
- **Grafana** - Dashboard ve gorsellestime

---

## Gereksinimler

| Yazilim | Versiyon | Indirme |
|---------|----------|---------|
| Python | 3.11+ | https://python.org |
| Node.js | 20+ LTS | https://nodejs.org |
| Docker Desktop | Latest | https://docker.com |
| Git | Latest | https://git-scm.com |
| Google Chrome | Latest | Scraper icin gerekli |

---

## Kurulum

### 1. Repoyu Klonla

```bash
git clone https://github.com/emrefkucuk/academic_research_analysis.git
cd academic_research_analysis
```

### 2. Docker Servislerini Baslat

```bash
cd scrapers
docker compose up -d
```

Bu komut asagidaki 7 servisi baslatir:

| Servis | Port | Aciklama |
|--------|------|----------|
| MongoDB | 27017 | Veritabani |
| Redis | 6440 | Cache & Streams |
| Elasticsearch | 9200 | Full-text arama motoru |
| Prometheus | 9090 | Metrik toplama |
| Grafana | 3001 | Monitoring dashboardlari |
| Mongo Express | 8081 | MongoDB web UI |
| Redis Commander | 8082 | Redis web UI |

Servislerin hazir oldugundan emin olmak icin:

```bash
docker compose ps
```

Tum servislerin `running` veya `healthy` durumunda olmasini bekleyin. Elasticsearch'un baslamasi ~60 saniye surebilir.

### 3. Python Bagimliklarini Yukle

```bash
cd scrapers
pip install -r requirements.txt
```

> **Not:** Bazi NLP kutuphaneleri (sentence-transformers, torch vb.) buyuk olabilir. Ilk kurulum ~1-2 GB indirir.

### 4. Backend .env Dosyasini Olustur

`scrapers/.env.example` dosyasini kopyalayarak baslayabilirsiniz:

```bash
cp .env.example .env
```

Veya `scrapers/.env` dosyasini asagidaki minimum ayarlarla olusturun:

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

# Scraper Ayarlari
AUTO_START_SCRAPERS=false
SCRAPER_HEADLESS=true

# NLP
NLP_LAZY_INIT=true
NLP_EMBEDDER_MODEL=all-MiniLM-L6-v2
```

Tum yapilandirma secenekleri icin `.env.example` dosyasina bakin.

### 5. Frontend Bagimliklarini Yukle

```bash
cd client
npm install
```

### 6. Frontend .env Dosyasi

`client/.env` dosyasi zaten mevcut olmalidir. Yoksa olusturun:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

---

## Calistirma

Projeyi calistirmak icin **3 ayri terminal** gereklidir:

### Terminal 1: Docker Servisleri

```bash
cd scrapers
docker compose up -d
```

### Terminal 2: Python Backend

```bash
cd scrapers
python run_backend.py
```

Basarili baslatmada su ciktiyi goreceksiniz:

```
BACKEND HAZIR
API: http://localhost:8000
Docs: http://localhost:8000/docs
```

### Terminal 3: Next.js Frontend

**Gelistirme modu** (hot-reload, sayfa gecisleri biraz yavas):

```bash
cd client
npm run dev
```

**Production modu** (hizli sayfa gecisleri, hot-reload yok):

```bash
cd client
npm run build
npm start
```

Frontend adresi: http://localhost:3000

---

## Servis Adresleri

| Servis | URL | Kullanici / Sifre |
|--------|-----|-------------------|
| Frontend | http://localhost:3000 | - |
| Backend API | http://localhost:8000 | - |
| Swagger API Docs | http://localhost:8000/docs | - |
| Mongo Express | http://localhost:8081 | admin / admin123 |
| Redis Commander | http://localhost:8082 | - |
| Grafana | http://localhost:3001 | admin / admin123 |
| Prometheus | http://localhost:9090 | - |

---

## Onemli Kullanim Notlari

### Veri Toplama (Scraper)

Sistem bos veritabani ile baslar. Makale toplamak icin:

1. Frontend'de **Scraper** sayfasina gidin
2. IEEE, ScienceDirect veya ACM scraperlarindan birini baslatin
3. Scraper durumunu WebSocket ile canli takip edebilirsiniz

### AI / NLP Analizi

NLP modulu **ilk kullanim sirasinda otomatik egitilir**:

1. **Arama** sayfasina gidin
2. Bir anahtar kelime girin (ornegin "machine learning")
3. **AI Analiz** butonuna basin
4. Eger model daha once egitilmemisse, otomatik egitim baslar (30sn - 5dk)
5. Egitim bittiginde cluster bilgisi, 3 grafik ve eslesen makaleler gorunur

> **Not:** Egitim icin veritabaninda en az ~20 abstract'li makale bulunmalidir. Yeterli makale yoksa once scraper calistirin.

### Atif Haritasi

**Atif Haritasi** sayfasi, makaleler arasi atif iliskilerini interaktif bir ag grafigi olarak gosterir. Bu ozelligin calismasi icin OpenAlex uzerinden atif verilerinin cekilmis olmasi gerekir.

---

## Proje Yapisi

```
academic_research_analysis/
|
+-- client/                          # Frontend (Next.js 15)
|   +-- app/                         # Sayfalar (App Router)
|   |   +-- page.tsx                 # Dashboard
|   |   +-- articles/                # Makale listesi & detay
|   |   +-- journals/                # Dergi listesi & detay
|   |   +-- authors/                 # Yazar profilleri
|   |   +-- search/                  # Arama + AI Analiz
|   |   +-- trends/                  # Trend grafikleri
|   |   +-- citation-map/            # Interaktif atif haritasi
|   |   +-- scrapers/                # Scraper kontrol paneli
|   +-- components/                  # React componentleri
|   |   +-- dashboard/               # Dashboard componentleri
|   |   +-- layout/                  # Sidebar navigasyon
|   |   +-- providers/               # WebSocket ScraperProvider
|   |   +-- ui/                      # Card, Badge, Button, Input
|   +-- lib/                         # API client, types, hooks
|
+-- scrapers/                        # Backend (Python)
    +-- backend/                     # FastAPI uygulamasi
    |   +-- core/                    # Config & middleware
    |   +-- routers/                 # API endpoint'leri
    |   +-- services/                # NLP, cache, scraper servisleri
    |   +-- schemas/                 # Pydantic response modelleri
    +-- database/                    # MongoDB
    |   +-- models/                  # Beanie ODM modelleri
    |   +-- repositories/            # Data access layer
    +-- ieee_xplore/                 # IEEE Xplore scraper
    +-- science_direct/              # ScienceDirect scraper
    +-- acm/                         # ACM Digital Library scraper
    +-- docker/                      # Docker yapilandirmalari
    |   +-- prometheus/              # Prometheus config
    |   +-- grafana/                 # Grafana dashboard & provisioning
    +-- tests/                       # pytest testleri
    +-- utils/                       # Logger ve yardimci moduller
    +-- docker-compose.yml
    +-- requirements.txt
    +-- run_backend.py               # Backend baslatma scripti
```

---

## API Endpoints

Tam liste icin Swagger UI'a bakin: http://localhost:8000/docs

### Stats
| Method | Endpoint | Aciklama |
|--------|----------|----------|
| GET | `/api/v1/stats` | Genel istatistikler |
| GET | `/api/v1/stats/articles` | Makale istatistikleri |
| GET | `/api/v1/stats/citations` | Atif istatistikleri |

### Journals
| Method | Endpoint | Aciklama |
|--------|----------|----------|
| GET | `/api/v1/journals` | Dergi listesi (paginated, filtreli) |
| GET | `/api/v1/journals/{id}` | Dergi detayi |
| GET | `/api/v1/journals/{id}/issues` | Derginin sayilari |
| GET | `/api/v1/journals/{id}/articles` | Derginin makaleleri |
| GET | `/api/v1/journals/{id}/citation-metrics` | Dergi atif metrikleri ve tarihsel grafik |

### Articles
| Method | Endpoint | Aciklama |
|--------|----------|----------|
| GET | `/api/v1/articles` | Makale listesi (paginated, filtreli) |
| GET | `/api/v1/articles/{id}` | Makale detayi |
| GET | `/api/v1/articles/{id}/citation-metrics` | Makale atif metrikleri |

### Search
| Method | Endpoint | Aciklama |
|--------|----------|----------|
| GET | `/api/v1/search?q=...` | Elasticsearch full-text arama |
| GET | `/api/v1/search/suggest?q=...` | Autocomplete onerileri |
| GET | `/api/v1/search/facets` | Arama facet'leri (kaynak, yil, dergi) |

### NLP / AI
| Method | Endpoint | Aciklama |
|--------|----------|----------|
| GET | `/api/v1/nlp/status` | NLP model durumu |
| GET | `/api/v1/nlp/search?query=...` | Semantik benzerlik aramasi |
| GET | `/api/v1/nlp/get_bar_chart_input` | Yil bazli makale dagilimi |
| GET | `/api/v1/nlp/get_pie_chart_input` | Konu dagilimi |
| GET | `/api/v1/nlp/get_scatter_chart_input` | 2D UMAP scatter verisi |
| POST | `/api/v1/nlp/train` | Manuel model egitimi |
| GET | `/api/v1/nlp/clusters` | Tum cluster'lari listele |

### Scrapers
| Method | Endpoint | Aciklama |
|--------|----------|----------|
| GET | `/api/v1/scrapers/status` | Tum scraper durumlari |
| POST | `/api/v1/scrapers/ieee/start` | IEEE scraper baslat |
| POST | `/api/v1/scrapers/ieee/stop` | IEEE scraper durdur |
| POST | `/api/v1/scrapers/sciencedirect/start` | ScienceDirect baslat |
| POST | `/api/v1/scrapers/acm/start` | ACM baslat |
| POST | `/api/v1/scrapers/start-all` | Tumunu baslat |
| POST | `/api/v1/scrapers/stop-all` | Tumunu durdur |

### Authors & Citations
| Method | Endpoint | Aciklama |
|--------|----------|----------|
| GET | `/api/v1/authors` | Yazar listesi |
| GET | `/api/v1/authors/{name}` | Yazar profili |
| GET | `/api/v1/citation-graph?article_id=...` | Atif grafigi verileri |

### WebSocket
| Endpoint | Aciklama |
|----------|----------|
| `ws://localhost:8000/ws/scrapers/events` | Canli scraper event stream |

---
