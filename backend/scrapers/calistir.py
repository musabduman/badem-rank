"""
scrapers/calistir.py — Cron tarafından çağrılan scrape giriş noktası
GitHub Actions ile her gece çalıştırılır:
    python -m scrapers.calistir
    python -m scrapers.calistir --keyword "crochet hat"
"""
import asyncio
import logging
import sys
import time
from database import supabase
from scrapers.etsy_arama import keyword_tam_scrape
from scrapers.kaydet import (
    listing_kaydet,
    gunluk_snapshot_kaydet,
    keyword_anlik_kaydet,
    scrape_log_baslat,
    scrape_log_bitir
)

# Log ayarları
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("scraper")


async def keyword_isle(keyword_id: str, keyword: str):
    """
    Tek bir keyword'ü tamamen scrape edip Supabase'e kaydeder.
    """
    log_id = await scrape_log_baslat(keyword)
    baslangic = time.time()
    logger.info(f"▶ Başladı: '{keyword}'")

    try:
        # 1. Scrape
        sonuc = await keyword_tam_scrape(keyword)
        listinglar = sonuc["listinglar"]
        logger.info(f"'{keyword}': {len(listinglar)} listing çekildi")

        # 2. Listing sayısı tahmini (çekilen * sayfa limiti)
        listing_sayisi_tahmini = len(listinglar) * 10  # kaba tahmin

        # 3. Listingleri kaydet
        basarili = 0
        for listing_verisi in listinglar:
            listing_id = await listing_kaydet(listing_verisi, keyword_id)
            if listing_id:
                await gunluk_snapshot_kaydet(listing_id, listing_verisi)
                basarili += 1

        # 4. Keyword anlık istatistik kaydet
        await keyword_anlik_kaydet(keyword_id, listinglar, listing_sayisi_tahmini)

        sure = time.time() - baslangic
        logger.info(f"✅ Tamamlandı: '{keyword}' — {basarili}/{len(listinglar)} listing, {sure:.1f}s")

        if log_id:
            await scrape_log_bitir(log_id, "basarili", basarili, sure)

    except Exception as e:
        sure = time.time() - baslangic
        logger.error(f"❌ Hata: '{keyword}' — {e}")
        if log_id:
            await scrape_log_bitir(log_id, "hata", 0, sure, str(e))


async def tumunu_tara(hedef_keyword: str = None):
    """
    Veritabanındaki tüm aktif keyword'leri sırayla tarar.
    hedef_keyword verilirse sadece onu tarar.
    """
    if hedef_keyword:
        # Belirli bir keyword için çalıştır
        yanit = supabase.table("keywords").select("*").eq("keyword", hedef_keyword).execute()
        keywords = yanit.data or []
        if not keywords:
            logger.error(f"'{hedef_keyword}' keyword bulunamadı. Önce ekle.")
            return
    else:
        # Tüm aktif keyword'ler
        yanit = supabase.table("keywords").select("*").eq("aktif", True).execute()
        keywords = yanit.data or []

    if not keywords:
        logger.warning("Taranacak aktif keyword yok. Supabase'e keyword ekle.")
        return

    logger.info(f"Toplam {len(keywords)} keyword taranacak")

    for kw in keywords:
        await keyword_isle(kw["id"], kw["keyword"])
        # Keyword'ler arası bekleme
        await asyncio.sleep(10)

    logger.info("🏁 Tüm keyword'ler tamamlandı")


if __name__ == "__main__":
    # Kullanım:
    #   python -m scrapers.calistir                    → tüm aktif keyword'ler
    #   python -m scrapers.calistir "crochet hat"      → sadece bu keyword
    hedef = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(tumunu_tara(hedef))
