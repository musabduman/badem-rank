"""
models/listing.py — Listing ile ilgili Pydantic modelleri
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime
import uuid


# ── Listing Response ───────────────────────────────────────────────────────────

class ListingYaniti(BaseModel):
    """Tekil listing response"""
    id: uuid.UUID
    etsy_listing_id: int
    keyword_id: Optional[uuid.UUID]
    magaza_adi: str
    baslik: str
    fiyat: Optional[float]
    para_birimi: str
    etiketler: Optional[List[str]]
    resim_url: Optional[str]
    favori_sayisi: int
    yorum_sayisi: int
    satis_tahmini: int
    star_seller_mi: bool
    magaza_yasi_gun: Optional[int]
    listing_url: Optional[str]
    ilk_goruldu: date
    son_guncellendi: date

    class Config:
        from_attributes = True


class GunlukAnlikYaniti(BaseModel):
    """Listing günlük snapshot ve delta değerleri"""
    id: uuid.UUID
    listing_id: uuid.UUID
    tarih: date
    favori_sayisi: int
    yorum_sayisi: int
    satis_tahmini: int
    gunluk_favori_degisim: int
    gunluk_yorum_degisim: int
    gunluk_satis_degisim: int

    class Config:
        from_attributes = True


class ListingDetayYaniti(BaseModel):
    """Listing + son 30 günlük delta geçmişi"""
    listing: ListingYaniti
    gunluk_gecmis: List[GunlukAnlikYaniti] = []


# ── Filtre / Sorgu Parametreleri ───────────────────────────────────────────────

class ListingFiltre(BaseModel):
    """GET /api/listings için query parametreleri"""
    keyword_id: Optional[uuid.UUID] = None
    min_fiyat: Optional[float] = None
    max_fiyat: Optional[float] = None
    sadece_star_seller: Optional[bool] = None
    siralama: str = Field("satis_tahmini", description="satis_tahmini | fiyat | favori_sayisi | yorum_sayisi")
    siralama_yonu: str = Field("desc", description="asc | desc")
    sayfa: int = Field(1, ge=1)
    sayfa_boyutu: int = Field(20, ge=1, le=100)


# ── Etiket Analizi ─────────────────────────────────────────────────────────────

class EtiketAnalizi(BaseModel):
    """Tek etiketin performans özeti"""
    etiket: str
    kullanim_sayisi: int                 # kaç listing'de geçiyor
    ort_satis_tahmini: float
    ort_fiyat: float
    toplam_favori: int
    star_seller_orani: float             # 0.0 - 1.0


class EtiketAnaliziYaniti(BaseModel):
    """Etiket analizi endpoint'i response'u"""
    keyword: str
    tarih: date
    etiketler: List[EtiketAnalizi]
