"""
models/rapor.py — LLM rapor ve chat modelleri
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime
import uuid


# ── Pazar Raporu ───────────────────────────────────────────────────────────────

class PazarRaporuYaniti(BaseModel):
    """Veritabanından çekilen LLM raporu"""
    id: uuid.UUID
    keyword_id: Optional[uuid.UUID]
    rapor_tarihi: date
    rapor_tipi: str
    icerik: str
    kullanilan_model: Optional[str]
    olusturuldu: datetime

    class Config:
        from_attributes = True


class RaporOlusturIstek(BaseModel):
    """POST /api/market/generate için request body"""
    keyword_id: uuid.UUID
    rapor_tipi: str = Field(
        "gunluk_ozet",
        description="gunluk_ozet | etiket_analizi | fiyat_analizi"
    )
    yeniden_olustur: bool = Field(
        False,
        description="True ise önbellekten okumak yerine yeni rapor üretir"
    )


# ── LLM Chat ───────────────────────────────────────────────────────────────────

class ChatMesaji(BaseModel):
    """Tek chat mesajı"""
    rol: str = Field(..., description="kullanici | asistan | sistem")
    icerik: str


class ChatIstek(BaseModel):
    """POST /api/llm/chat için request body"""
    mesaj: str = Field(..., min_length=1, max_length=2000)
    keyword_baglami: Optional[str] = Field(
        None,
        description="Mevcut sayfanın keyword'ü — LLM'e bağlam verir"
    )
    gecmis: List[ChatMesaji] = Field(
        default_factory=list,
        max_length=20,
        description="Son 20 mesaj geçmişi (frontend localStorage'dan gelir)"
    )


class ChatYaniti(BaseModel):
    """POST /api/llm/chat için response (non-streaming)"""
    yanit: str
    model: str
    token_kullanimi: Optional[int] = None
