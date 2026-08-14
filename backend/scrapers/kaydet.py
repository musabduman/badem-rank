"""
scrapers/kaydet.py — Scrape edilen verileri Supabase'e kaydeder
Upsert mantığı: aynı etsy_listing_id varsa güncelle, yoksa ekle.
Günlük snapshot'ı kaydedip delta hesaplar.
"""
import logging
from datetime import date
from typing import Optional
from database import supabase
from services.analitik_service import gunluk_delta_hesapla, rekabet_skoru_hesapla

logger = logging.getLogger(__name__)


async def listing_kaydet(listing_verisi: dict, keyword_id: str) -> Optional[str]:
    """
    Tek bir listing'i Supabase'e upsert eder.
    
    Returns:
        Listing'in UUID'si veya hata durumunda None
    """
    bugun = date.today().isoformat()

    upsert_verisi = {
        **listing_verisi,
        "keyword_id": keyword_id,
        "son_guncellendi": bugun
    }

    # ilk_goruldu sadece INSERT'te set edilmeli, UPDATE'te değişmemeli
    # Supabase upsert onConflict ile bunu sağlıyoruz
    try:
        yanit = (
            supabase.table("listinglar")
            .upsert(
                upsert_verisi,
                on_conflict="etsy_listing_id",
                ignore_duplicates=False
            )
            .execute()
        )

        if yanit.data:
            return yanit.data[0]["id"]
        return None

    except Exception as e:
        logger.error(f"Listing kaydetme hatası (etsy_id={listing_verisi.get('etsy_listing_id')}): {e}")
        return None


async def gunluk_snapshot_kaydet(listing_id: str, listing_verisi: dict) -> bool:
    """
    Bir listing için günlük snapshot kaydeder ve delta hesaplar.
    
    Returns:
        True: başarılı, False: hata
    """
    bugun = date.today()

    snapshot_verisi = {
        "listing_id": listing_id,
        "tarih": bugun.isoformat(),
        "favori_sayisi": listing_verisi.get("favori_sayisi", 0),
        "yorum_sayisi": listing_verisi.get("yorum_sayisi", 0),
        "satis_tahmini": listing_verisi.get("satis_tahmini", 0)
    }

    # Delta hesapla (dünkü snapshot ile karşılaştır)
    delta = await gunluk_delta_hesapla(listing_id, bugun)
    snapshot_verisi.update(delta)

    try:
        supabase.table("listing_gunluk_anliklari").upsert(
            snapshot_verisi,
            on_conflict="listing_id,tarih"
        ).execute()
        return True
    except Exception as e:
        logger.error(f"Günlük snapshot hatası (listing_id={listing_id}): {e}")
        return False


async def keyword_anlik_kaydet(
    keyword_id: str,
    listinglar: list[dict],
    listing_sayisi: int
) -> bool:
    """
    Keyword bazında günlük istatistik snapshot'ı kaydeder.
    
    Args:
        keyword_id: UUID
        listinglar: scrape edilen listing listesi
        listing_sayisi: Etsy'deki toplam sonuç sayısı tahmini
    """
    if not listinglar:
        return False

    bugun = date.today().isoformat()
    fiyatlar = [l["fiyat"] for l in listinglar if l.get("fiyat")]
    star_seller_sayisi = sum(1 for l in listinglar if l.get("star_seller_mi"))

    ort_fiyat = round(sum(fiyatlar) / len(fiyatlar), 2) if fiyatlar else None
    rekabet = await rekabet_skoru_hesapla(listing_sayisi, star_seller_sayisi)

    anlik_verisi = {
        "keyword_id": keyword_id,
        "cekilme_tarihi": bugun,
        "listing_sayisi": listing_sayisi,
        "ort_fiyat": ort_fiyat,
        "min_fiyat": min(fiyatlar) if fiyatlar else None,
        "max_fiyat": max(fiyatlar) if fiyatlar else None,
        "star_seller_sayisi": star_seller_sayisi,
        "ilk_sayfa_listing_sayisi": len(listinglar),
        "rekabet_skoru": rekabet
    }

    try:
        supabase.table("keyword_anliklari").upsert(
            anlik_verisi,
            on_conflict="keyword_id,cekilme_tarihi"
        ).execute()
        return True
    except Exception as e:
        logger.error(f"Keyword anlık kaydetme hatası (keyword_id={keyword_id}): {e}")
        return False


async def scrape_log_baslat(keyword: str) -> Optional[str]:
    """Yeni bir scrape log kaydı başlatır, log_id döner."""
    try:
        yanit = supabase.table("scrape_loglari").insert({
            "keyword": keyword,
            "durum": "devam_ediyor"
        }).execute()
        return yanit.data[0]["id"] if yanit.data else None
    except Exception as e:
        logger.error(f"Scrape log başlatma hatası: {e}")
        return None


async def scrape_log_bitir(
    log_id: str,
    durum: str,
    cekilen_listing: int,
    sure_saniye: float,
    hata_mesaji: Optional[str] = None
):
    """Mevcut scrape log kaydını günceller."""
    try:
        from datetime import datetime
        supabase.table("scrape_loglari").update({
            "durum": durum,
            "cekilen_listing": cekilen_listing,
            "sure_saniye": round(sure_saniye, 2),
            "bitis_zamani": datetime.now().isoformat(),
            "hata_mesaji": hata_mesaji
        }).eq("id", log_id).execute()
    except Exception as e:
        logger.error(f"Scrape log güncelleme hatası: {e}")
