"""
routers/listinglar.py — Listing görüntüleme ve filtreleme endpoint'leri
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from database import supabase
from models.listing import ListingYaniti, ListingDetayYaniti, GunlukAnlikYaniti
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/listinglar", tags=["Listinglar"])

# İzin verilen sıralama sütunları (SQL injection önlemi)
SIRALAMA_ALANLARI = {"satis_tahmini", "fiyat", "favori_sayisi", "yorum_sayisi", "ilk_goruldu"}


@router.get("", response_model=List[ListingYaniti])
async def listing_listesi(
    keyword_id: Optional[str] = Query(None),
    min_fiyat: Optional[float] = Query(None, ge=0),
    max_fiyat: Optional[float] = Query(None, ge=0),
    sadece_star_seller: Optional[bool] = Query(None),
    siralama: str = Query("satis_tahmini"),
    siralama_yonu: str = Query("desc"),
    sayfa: int = Query(1, ge=1),
    sayfa_boyutu: int = Query(20, ge=1, le=100)
):
    """
    Listing listesi — filtrelenebilir, sıralanabilir, sayfalanabilir.
    Frontend'deki ana tablo için kullanılır.
    """
    if siralama not in SIRALAMA_ALANLARI:
        raise HTTPException(status_code=400, detail=f"Geçersiz sıralama alanı. İzin verilenler: {SIRALAMA_ALANLARI}")

    artan = siralama_yonu.lower() == "asc"
    offset = (sayfa - 1) * sayfa_boyutu

    sorgu = supabase.table("listinglar").select("*")

    # Filtreler
    if keyword_id:
        sorgu = sorgu.eq("keyword_id", keyword_id)
    if min_fiyat is not None:
        sorgu = sorgu.gte("fiyat", min_fiyat)
    if max_fiyat is not None:
        sorgu = sorgu.lte("fiyat", max_fiyat)
    if sadece_star_seller is not None:
        sorgu = sorgu.eq("star_seller_mi", sadece_star_seller)

    yanit = (
        sorgu
        .order(siralama, desc=not artan)
        .range(offset, offset + sayfa_boyutu - 1)
        .execute()
    )

    return yanit.data or []


@router.get("/en-cok-satan", response_model=List[ListingYaniti])
async def en_cok_satan(
    keyword_id: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50)
):
    """
    En yüksek satış tahminli listing'leri döner.
    Keyword istatistik kartlarındaki 'Top Sellers' bölümü için.
    """
    sorgu = supabase.table("listinglar").select("*")
    if keyword_id:
        sorgu = sorgu.eq("keyword_id", keyword_id)

    yanit = sorgu.order("satis_tahmini", desc=True).limit(limit).execute()
    return yanit.data or []


@router.get("/{listing_id}", response_model=ListingDetayYaniti)
async def listing_detay(listing_id: str):
    """
    Tek listing + 30 günlük günlük snapshot geçmişi.
    Listing detay modal'ı için.
    """
    listing_yanit = supabase.table("listinglar").select("*").eq("id", listing_id).execute()
    if not listing_yanit.data:
        raise HTTPException(status_code=404, detail="Listing bulunamadı")

    gecmis_yanit = (
        supabase.table("listing_gunluk_anliklari")
        .select("*")
        .eq("listing_id", listing_id)
        .order("tarih", desc=True)
        .limit(30)
        .execute()
    )

    return {
        "listing": listing_yanit.data[0],
        "gunluk_gecmis": gecmis_yanit.data or []
    }


@router.get("/{listing_id}/anliklari", response_model=List[GunlukAnlikYaniti])
async def listing_gunluk_anliklari(listing_id: str, gun: int = Query(30, ge=1, le=90)):
    """
    Listing'in günlük delta verilerini döner.
    Trend grafiği için kullanılır.
    """
    yanit = (
        supabase.table("listing_gunluk_anliklari")
        .select("*")
        .eq("listing_id", listing_id)
        .order("tarih", desc=False)  # Grafik için artan sıra
        .limit(gun)
        .execute()
    )
    return yanit.data or []
