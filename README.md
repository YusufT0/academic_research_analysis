# 📚 Yapay Zeka Destekli Bilimsel Dergilerin Trend Analiz Sistemi

**BM495 Bilgisayar Mühendisliği Projesi I - 2025-2026 Güz**

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
# ======== MongoDB ========
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=academic_research
# Eğer authentication varsa:
# MONGODB_USERNAME=admin
# MONGODB_PASSWORD=password

# ======== Scraper ========
# Backend başladığında scraper otomatik başlasın mı
AUTO_START_SCRAPERS=false

# Browser görünmez modda çalışsın mı (true önerilir)
SCRAPER_HEADLESS=true

# Scraper'lar paralel mi sıralı mı çalışsın
# parallel: Aynı anda çalışır
# sequential: Önce IEEE biter, sonra ScienceDirect başlar
SCRAPER_RUN_MODE=parallel

# Her dergiden maksimum kaç makale çekilsin
IEEE_MAX_ARTICLES=10
SCIENCEDIRECT_MAX_ARTICLES=5
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

Bu proje Sakarya Üniversitesi Bilgisayar Mühendisliği Bölümü BM495 dersi kapsamında geliştirilmiştir.

---

## 📧 İletişim

Sorularınız için: [GitHub Issues](https://github.com/emrefkucuk/academic_research_analysis/issues)

