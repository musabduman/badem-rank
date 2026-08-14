"""
routers/analitik.py — Pazar analizi endpoint'leri
Etiket performansı, fiyat dağılımı, rekabet analizi, günlük delta tablosu.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import date
from database import supabase
from services.analitik_service import etiket_analizi_hesapla, fiyat_analizi_hesapla
from models.listing import EtiketAnaliziYaniti
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analitik", tags=["Analitik"])


@router.get("/etiketler")
async def etiket_analizi(keyword_id: str = Query(...)):
    """
    Bir keyword'ün en iyi performans gösteren etiketlerini döner.
    Hangi tag kombinasyonlarının daha çok satış getirdiğini gösterir.
    """
    # Keyword var mı?
    kw = supabase.table("keywords").select("keyword").eq("id", keyword_id).execute()
    if not kw.data:
        raise HTTPException(status_code=404, detail="Keyword bulunamadı")

    etiketler = await etiket_analizi_hesapla(keyword_id)

    return {
        "keyword": kw.data[0]["keyword"],
        "tarih": date.today().isoformat(),
        "etiketler": etiketler
    }


@router.get("/fiyat")
async def fiyat_analizi(keyword_id: str = Query(...)):
    """
    Keyword için fiyat dağılımı istatistikleri.
    Fiyat segmentleri ve medyan döner.
    """
    kw = supabase.table("keywords").select("keyword").eq("id", keyword_id).execute()
    if not kw.data:
        raise HTTPException(status_code=404, detail="Keyword bulunamadı")

    fiyat_verisi = await fiyat_analizi_hesapla(keyword_id)

    return {
        "keyword": kw.data[0]["keyword"],
        "tarih": date.today().isoformat(),
        **fiyat_verisi
    }


@router.get("/gunluk-delta")
async def gunluk_delta_tablosu(
    keyword_id: str = Query(...),
    tarih: Optional[str] = Query(None, description="YYYY-MM-DD formatı, boş bırakılırsa bugün")
):
    """
    Belirli tarih için keyword'ün tüm listing'lerinin günlük değişimini döner.
    'Günlük satış' tablosu için kullanılır.
    """
    hedef_tarih = tarih or date.today().isoformat()

    # Keyword'ün listing_id listesi
    listing_yanit = (
        supabase.table("listinglar")
        .select("id, magaza_adi, baslik, fiyat, listing_url")
        .eq("keyword_id", keyword_id)
        .execute()
    )
    listing_map = {l["id"]: l for l in (listing_yanit.data or [])}

    if not listing_map:
        return {"tarih": hedef_tarih, "veriler": []}

    # O günkü tüm snapshot'ları çek
    delta_yanit = (
        supabase.table("listing_gunluk_anliklari")
        .select("*")
        .in_("listing_id", list(listing_map.keys()))
        .eq("tarih", hedef_tarih)
        .order("gunluk_satis_degisim", desc=True)
        .execute()
    )

    # Listing bilgileri ile birleştir
    sonuclar = []
    for delta in (delta_yanit.data or []):
        listing_bilgi = listing_map.get(delta["listing_id"], {})
        sonuclar.append({
            **delta,
            "magaza_adi": listing_bilgi.get("magaza_adi"),
            "baslik": listing_bilgi.get("baslik"),
            "fiyat": listing_bilgi.get("fiyat"),
            "listing_url": listing_bilgi.get("listing_url")
        })

    return {"tarih": hedef_tarih, "veriler": sonuclar}


@router.get("/rekabet")
async def rekabet_analizi(keyword_id: str = Query(...)):
    """
    Keyword'ün son rekabet skorunu ve geçmiş trendini döner.
    """
    trend = (
        supabase.table("keyword_anliklari")
        .select("cekilme_tarihi, rekabet_skoru, listing_sayisi, star_seller_sayisi, ort_fiyat")
        .eq("keyword_id", keyword_id)
        .order("cekilme_tarihi", desc=True)
        .limit(30)
        .execute()
    )

    return {
        "gecmis": trend.data or [],
        "son_skor": trend.data[0]["rekabet_skoru"] if trend.data else None
    }
