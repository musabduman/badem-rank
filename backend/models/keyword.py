"""
models/keyword.py — Keyword ile ilgili Pydantic modelleri
Request body'leri ve response şemaları burada tanımlanır.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime
import uuid


# ── Keyword Oluşturma ──────────────────────────────────────────────────────────

class KeywordOlustur(BaseModel):
    """POST /api/keywords için request body"""
    keyword: str = Field(..., min_length=1, max_length=200, examples=["crochet hat"])
    kategori: Optional[str] = Field(None, examples=["el örgüsü"])
    aciklama: Optional[str] = None


class KeywordGuncelle(BaseModel):
    """PATCH /api/keywords/{id} için request body"""
    kategori: Optional[str] = None
    aciklama: Optional[str] = None
    aktif: Optional[bool] = None


# ── Keyword Response ───────────────────────────────────────────────────────────

class KeywordYaniti(BaseModel):
    """Tekil keyword response"""
    id: uuid.UUID
    keyword: str
    kategori: Optional[str]
    aciklama: Optional[str]
    aktif: bool
    olusturuldu: datetime
    guncellendi: datetime

    class Config:
        from_attributes = True


class KeywordAnlikYaniti(BaseModel):
    """Keyword anlık istatistik snapshot'ı"""
    id: uuid.UUID
    keyword_id: uuid.UUID
    cekilme_tarihi: date
    listing_sayisi: Optional[int]
    ort_fiyat: Optional[float]
    min_fiyat: Optional[float]
    max_fiyat: Optional[float]
    star_seller_sayisi: Optional[int]
    ilk_sayfa_listing_sayisi: Optional[int]
    rekabet_skoru: Optional[int]

    class Config:
        from_attributes = True


class KeywordDetayYaniti(BaseModel):
    """Keyword + son snapshot birleşik response"""
    keyword: KeywordYaniti
    son_anlik: Optional[KeywordAnlikYaniti]
    trend_verisi: list[KeywordAnlikYaniti] = []  # 30 günlük geçmiş
