"""
database.py — Supabase bağlantısı
Supabase client'ını tek yerden oluşturur, her modül buradan import eder.
"""
from supabase import create_client, Client
from config import ayarlar
import logging

logger = logging.getLogger(__name__)

# Supabase client — uygulama genelinde tek örnek (singleton)
supabase: Client = create_client(
    supabase_url=ayarlar.supabase_url,
    supabase_key=ayarlar.supabase_key
)


def supabase_al() -> Client:
    """FastAPI dependency injection için client döner."""
    return supabase


def baglantiyi_test_et() -> bool:
    """Başlangıçta bağlantıyı doğrular."""
    try:
        supabase.table("keywords").select("id").limit(1).execute()
        logger.info("✅ Supabase bağlantısı başarılı")
        return True
    except Exception as e:
        logger.error(f"❌ Supabase bağlantı hatası: {e}")
        return False
