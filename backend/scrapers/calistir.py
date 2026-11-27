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
import httpx
from config import ayarlar
from database import supabase
from scrapers.etsy_arama import keyword_tam_scrape
from scrapers.kaydet import (
    toplu_listing_ve_snapshot_kaydet,
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

        # 3. Listingleri toplu ve thread üzerinde kaydet (ana döngüyü dondurmaz)
        basarili = await toplu_listing_ve_snapshot_kaydet(listinglar, keyword_id)

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


async def magazalari_tara():
    """
    Takip edilen tüm mağazaların (takip_aktif=True) günlük ürün ve satış verilerini günceller.
    Kullanıcının takip dışı bıraktığı ürünler (takip_aktif=False) korunur.
    """
    if not ayarlar.etsy_api_key:
        logger.warning("ETSY_API_KEY tanımlı değil — günlük mağaza taraması atlanıyor.")
        return

    from routers.magazalar import magaza_urunlerini_senkronize_et

    try:
        yanit = supabase.table("magazalar").select("*").eq("takip_aktif", True).execute()
        magazalar = yanit.data or []
    except Exception as e:
        logger.error(f"Takip edilen mağazalar okunamadı: {e}")
        return

    if not magazalar:
        logger.info("Takip edilen aktif mağaza yok.")
        return

    logger.info(f"Toplam {len(magazalar)} takip edilen mağaza güncellenecek")
    async with httpx.AsyncClient(timeout=20.0) as client:
        for m in magazalar:
            try:
                await magaza_urunlerini_senkronize_et(
                    sb=supabase,
                    magaza_id=m["id"],
                    shop_id=m["shop_id"],
                    mevcut_dislamalari_koru=True,
                    client=client,
                )
            except Exception as e:
                logger.error(f"Mağaza '{m.get('shop_name')}' güncellenemedi: {e}")
            await asyncio.sleep(1)

    logger.info("🏪 Takip edilen mağazalar güncellendi")


async def tumunu_tara(hedef_keyword: str = None):
    """
    Veritabanındaki tüm aktif keyword'leri sırayla tarar.
    hedef_keyword verilmezse takip edilen mağazaları da günlük günceller.
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

    if keywords:
        logger.info(f"Toplam {len(keywords)} keyword taranacak")
        for kw in keywords:
            await keyword_isle(kw["id"], kw["keyword"])
            await asyncio.sleep(10)
    else:
        logger.warning("Taranacak aktif keyword yok.")

    if not hedef_keyword:
        await magazalari_tara()

    logger.info("🏁 Günlük tarama tamamlandı")


if __name__ == "__main__":
    # Kullanım:
    #   python -m scrapers.calistir                    → tüm aktif keyword'ler
    #   python -m scrapers.calistir "crochet hat"      → sadece bu keyword
    hedef = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(tumunu_tara(hedef))
