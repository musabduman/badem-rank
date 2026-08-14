"""
main.py — FastAPI uygulama giriş noktası
Tüm router'ları kayıt eder, CORS ayarlar, başlangıç kontrollerini yapar.
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import ayarlar
from database import baglantiyi_test_et
from routers import keywords, listinglar, analitik, llm, sistem

# Log ayarları
logging.basicConfig(
    level=getattr(logging, ayarlar.app_log_seviyesi),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("main")


@asynccontextmanager
async def yasam_dongusu(app: FastAPI):
    """Uygulama başlarken çalışır."""
    logger.info("🚀 Badem Rank API başlatılıyor...")
    baglantiyi_test_et()
    logger.info(f"📡 Ortam: {ayarlar.app_ortam}")
    logger.info(f"🤖 LLM modeli: {ayarlar.ollama_model}")
    yield
    logger.info("🛑 Uygulama kapatılıyor...")


# FastAPI uygulaması
app = FastAPI(
    title="Badem Rank API",
    description="Etsy pazar analiz aracı — keyword, listing ve trend verisi",
    version="1.0.0",
    docs_url="/docs",           # Swagger UI
    redoc_url="/redoc",         # ReDoc
    lifespan=yasam_dongusu
)

# CORS — Frontend'in farklı origin'den istek atabilmesi için
app.add_middleware(
    CORSMiddleware,
    allow_origins=ayarlar.izin_listesi,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Router'ları kayıt et
app.include_router(keywords.router)
app.include_router(listinglar.router)
app.include_router(analitik.router)
app.include_router(llm.router)
app.include_router(sistem.router)


@app.get("/")
async def ana_sayfa():
    return {
        "uygulama": "Badem Rank API",
        "versiyon": "1.0.0",
        "docs": "/docs"
    }
