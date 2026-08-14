"""
routers/keywords.py — Keyword CRUD ve tarihsel veri endpoint'leri
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List, Optional
from database import supabase
from models.keyword import KeywordOlustur, KeywordGuncelle, KeywordYaniti, KeywordDetayYaniti, KeywordAnlikYaniti
from scrapers.calistir import keyword_isle
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/keywords", tags=["Keywords"])


@router.get("", response_model=List[KeywordDetayYaniti])
async def keyword_listesi():
    """
    Tüm keyword'leri son snapshot bilgileriyle döner.
    Dashboard'daki keyword listesi için kullanılır.
    """
    # Tüm keyword'leri çek
    kw_yanit = supabase.table("keywords").select("*").order("olusturuldu", desc=True).execute()
    keywords = kw_yanit.data or []

    sonuclar = []
    for kw in keywords:
        # Her keyword için son snapshot'ı çek
        anlik_yanit = (
            supabase.table("keyword_anliklari")
            .select("*")
            .eq("keyword_id", kw["id"])
            .order("cekilme_tarihi", desc=True)
            .limit(1)
            .execute()
        )
        son_anlik = anlik_yanit.data[0] if anlik_yanit.data else None

        sonuclar.append({
            "keyword": kw,
            "son_anlik": son_anlik,
            "trend_verisi": []
        })

    return sonuclar


@router.post("", response_model=KeywordYaniti, status_code=201)
async def keyword_ekle(veri: KeywordOlustur, background_tasks: BackgroundTasks):
    """
    Yeni keyword ekler ve arka planda scrape başlatır.
    """
    # Aynı keyword var mı kontrol et
    mevcut = (
        supabase.table("keywords")
        .select("id")
        .eq("keyword", veri.keyword.lower().strip())
        .execute()
    )
    if mevcut.data:
        raise HTTPException(status_code=409, detail=f"'{veri.keyword}' zaten ekli")

    # Kaydet
    yanit = supabase.table("keywords").insert({
        "keyword": veri.keyword.lower().strip(),
        "kategori": veri.kategori,
        "aciklama": veri.aciklama
    }).execute()

    if not yanit.data:
        raise HTTPException(status_code=500, detail="Keyword kaydedilemedi")

    yeni_kw = yanit.data[0]

    # Arka planda ilk scrape'i başlat
    background_tasks.add_task(keyword_isle, yeni_kw["id"], yeni_kw["keyword"])
    logger.info(f"Yeni keyword eklendi ve scrape başlatıldı: '{veri.keyword}'")

    return yeni_kw


@router.get("/{keyword_id}", response_model=KeywordDetayYaniti)
async def keyword_detay(keyword_id: str, gun: int = 30):
    """
    Tek keyword + son N günlük trend verisi.
    """
    kw_yanit = supabase.table("keywords").select("*").eq("id", keyword_id).execute()
    if not kw_yanit.data:
        raise HTTPException(status_code=404, detail="Keyword bulunamadı")

    # Trend verisi (son N gün)
    trend_yanit = (
        supabase.table("keyword_anliklari")
        .select("*")
        .eq("keyword_id", keyword_id)
        .order("cekilme_tarihi", desc=True)
        .limit(gun)
        .execute()
    )

    trend = trend_yanit.data or []
    son_anlik = trend[0] if trend else None

    return {
        "keyword": kw_yanit.data[0],
        "son_anlik": son_anlik,
        "trend_verisi": trend
    }


@router.patch("/{keyword_id}", response_model=KeywordYaniti)
async def keyword_guncelle(keyword_id: str, veri: KeywordGuncelle):
    """Keyword kategori/açıklama/aktiflik günceller."""
    guncelleme = {k: v for k, v in veri.model_dump().items() if v is not None}
    if not guncelleme:
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok")

    yanit = supabase.table("keywords").update(guncelleme).eq("id", keyword_id).execute()
    if not yanit.data:
        raise HTTPException(status_code=404, detail="Keyword bulunamadı")

    return yanit.data[0]


@router.delete("/{keyword_id}", status_code=204)
async def keyword_sil(keyword_id: str):
    """Keyword ve tüm bağlı verileri siler (CASCADE)."""
    yanit = supabase.table("keywords").delete().eq("id", keyword_id).execute()
    if not yanit.data:
        raise HTTPException(status_code=404, detail="Keyword bulunamadı")
