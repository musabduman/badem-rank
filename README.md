# 🌰 Badem Rank

Etsy pazar analizi aracı. E-Rank benzeri yapı — keyword araştırma, listing takibi, günlük satış delta hesabı ve AI destekli pazar yorumu.

---

## 📐 Mimari

```
Frontend (HTML/CSS/JS)  →  Vercel
Backend  (FastAPI)      →  Render
Database (PostgreSQL)   →  Supabase
Scraper  (Python)       →  GitHub Actions (her gece 02:00 TR)
LLM      (Ollama API)   →  Kendi sunucun
```

---

## 🗂️ Proje Yapısı

```
badem-rank/
├── backend/
│   ├── main.py                  # FastAPI giriş noktası
│   ├── config.py                # Environment variable yönetimi
│   ├── database.py              # Supabase client
│   ├── models/                  # Pydantic şemaları
│   │   ├── keyword.py
│   │   ├── listing.py
│   │   └── rapor.py
│   ├── routers/                 # API endpoint'leri
│   │   ├── keywords.py          # /api/keywords
│   │   ├── listinglar.py        # /api/listinglar
│   │   ├── analitik.py          # /api/analitik
│   │   ├── llm.py               # /api/llm
│   │   └── sistem.py            # /api/sistem
│   ├── services/                # İş mantığı
│   │   ├── analitik_service.py  # Etiket/fiyat/rekabet hesapları
│   │   └── llm_service.py       # Ollama streaming
│   ├── scrapers/                # Veri çekme
│   │   ├── etsy_arama.py        # Etsy arama sayfası parser
│   │   ├── kaydet.py            # Supabase upsert katmanı
│   │   └── calistir.py          # Cron entry point
│   └── requirements.txt
├── frontend/                    # (Phase 2 — yapılacak)
├── scripts/
│   └── setup_db.sql             # Supabase şeması
└── .github/
    └── workflows/
        └── gunluk_scrape.yml    # Günlük scrape cron'u
```

---

## 🚀 Kurulum

### 1. Supabase Şemasını Kur

Supabase dashboard → SQL Editor → `scripts/setup_db.sql` dosyasını çalıştır.

### 2. Environment Değişkenlerini Ayarla

```bash
cd backend
cp .env.example .env
```

`.env` dosyasını düzenle:

```env
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=eyJ...
OLLAMA_API_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
```

### 3. Python Bağımlılıklarını Yükle

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux

pip install -r requirements.txt
```

### 4. Sunucuyu Başlat

```bash
cd backend
uvicorn main:app --reload --port 8000
```

API dokümantasyonu: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 📊 Veritabanı Şeması

| Tablo | Açıklama |
|---|---|
| `keywords` | Takip edilen arama kelimeleri |
| `keyword_anliklari` | Günlük keyword istatistikleri (listing sayısı, ort. fiyat, rekabet skoru) |
| `listinglar` | Etsy'den çekilen ürün listelemeleri |
| `listing_gunluk_anliklari` | Günlük delta değerleri (satış/favori değişimi) |
| `pazar_raporlari` | LLM tarafından üretilen analiz raporları (önbellekli) |
| `scrape_loglari` | Her scrape işleminin kayıtları |

### Günlük Satış Tahmini Nasıl Çalışır?

Etsy satış sayısını direkt göstermez. Sistem şu mantıkla çalışır:

```
Listing A — bugün scrape:  satis_tahmini = 145
Listing A — dün scrape:    satis_tahmini = 138
→ gunluk_satis_degisim = 7
```

---

## 🔌 API Endpoint'leri

### Keywords
| Method | Endpoint | Açıklama |
|---|---|---|
| GET | `/api/keywords` | Tüm keyword'ler + son snapshot |
| POST | `/api/keywords` | Yeni keyword ekle (scrape tetikler) |
| GET | `/api/keywords/{id}` | Keyword detay + 30 günlük trend |
| PATCH | `/api/keywords/{id}` | Güncelle |
| DELETE | `/api/keywords/{id}` | Sil |

### Listinglar
| Method | Endpoint | Açıklama |
|---|---|---|
| GET | `/api/listinglar` | Filtrelenebilir listing listesi |
| GET | `/api/listinglar/en-cok-satan` | Top seller'lar |
| GET | `/api/listinglar/{id}` | Listing detay + delta geçmişi |

### Analitik
| Method | Endpoint | Açıklama |
|---|---|---|
| GET | `/api/analitik/etiketler?keyword_id=` | Etiket performans analizi |
| GET | `/api/analitik/fiyat?keyword_id=` | Fiyat dağılımı |
| GET | `/api/analitik/gunluk-delta?keyword_id=` | Günlük satış delta tablosu |
| GET | `/api/analitik/rekabet?keyword_id=` | Rekabet skoru trendi |

### LLM
| Method | Endpoint | Açıklama |
|---|---|---|
| POST | `/api/llm/chat` | Streaming chat (SSE) |
| POST | `/api/llm/rapor-olustur` | Pazar raporu üret (önbellekli) |
| GET | `/api/llm/raporlar/{keyword_id}` | Geçmiş raporlar |

### Sistem
| Method | Endpoint | Açıklama |
|---|---|---|
| GET | `/api/sistem/saglik` | Sağlık kontrolü |
| POST | `/api/sistem/scrape/baslat` | Manuel scrape tetikle |
| GET | `/api/sistem/scrape/loglar` | Scrape logları |

---

## ⚙️ Scraper Kullanımı

```bash
cd backend

# Tüm aktif keyword'leri tara
python -m scrapers.calistir

# Sadece belirli bir keyword'ü tara
python -m scrapers.calistir "crochet hat"
```

**Otomatik Çalışma:** GitHub Actions her gece 02:00 TR saatinde `gunluk_scrape.yml` workflow'unu çalıştırır.

GitHub repo → Settings → Secrets'a şunları ekle:
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `OLLAMA_API_URL` (opsiyonel — LLM raporu için)

---

## 🤖 LLM Entegrasyonu

Ollama API'nin OpenAI-uyumlu endpoint'ini kullanır.

```env
OLLAMA_API_URL=http://your-ollama-server:11434
OLLAMA_MODEL=llama3.1:8b
```

**Kullanım senaryoları:**
- Sağ panel AI chat — kullanıcının sorularını güncel veri bağlamıyla yanıtlar
- Günlük pazar özeti raporu — etiket ve fiyat verilerini yorumlar
- Etiket stratejisi önerisi — hangi tag'lerin daha iyi performans gösterdiğini açıklar

---

## 🌐 Deploy

### Backend → Render

1. Render'da **Web Service** oluştur
2. Build Command: `pip install -r backend/requirements.txt`
3. Start Command: `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Environment Variables'ı ekle

### Frontend → Vercel

```bash
cd frontend
vercel --prod
```

---

## 📝 Notlar

- Etsy'nin public arama sayfaları scrape edilir (login gerektirmez)
- Rate limiting: request'ler arası 2-5 sn rastgele bekleme
- Scraper, keyword başına max 3 sayfa (~90 listing) çeker
- Aynı listing günde birden fazla scrape edilirse `upsert` ile güncellenir
