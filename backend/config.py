"""
config.py — Uygulama ayarları
Tüm environment variable'lar buradan okunur, başka dosyalar .env'e doğrudan bakmamalı.
"""
from pydantic_settings import BaseSettings
from typing import List


class Ayarlar(BaseSettings):
    # Supabase
    supabase_url: str
    supabase_key: str

    # Ollama LLM
    ollama_api_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    # Scraper
    scrape_bekleme_min: int = 2          # saniye (min bekleme)
    scrape_bekleme_max: int = 5          # saniye (max bekleme)
    scrape_sayfa_limiti: int = 3         # keyword başına max sayfa

    # Uygulama
    app_ortam: str = "development"
    app_log_seviyesi: str = "INFO"
    izin_verilen_originler: str = "http://localhost:3000"

    @property
    def izin_listesi(self) -> List[str]:
        """CORS için izin verilen origin listesi"""
        return [o.strip() for o in self.izin_verilen_originler.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global ayarlar nesnesi — her modül buradan import eder
ayarlar = Ayarlar()
