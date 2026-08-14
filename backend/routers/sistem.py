"""
routers/sistem.py — Sistem durumu, scrape tetikleme ve loglar
"""
from fastapi import APIRouter, BackgroundTasks, Query
from database import supabase, baglantiyi_test_et
from scrapers.calistir import tumunu_tara, keyword_isle
from config import ayarlar
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sistem", tags=["Sistem"])


@router.get("/saglik")
async def saglik_kontrolu():
    """
    Uygulama ve Supabase bağlantısı sağlık kontrolü.
    Render health check endpoint'i olarak da kullanılır.
    """
    supabase_ok = baglantiyi_test_et()
    return {
        "durum": "calisiyor",
        "supabase": "bagli" if supabase_ok else "hata",
        "model": ayarlar.ollama_model,
        "ortam": ayarlar.app_ortam
    }


@router.post("/scrape/baslat")
async def scrape_baslat(
    background_tasks: BackgroundTasks,
    keyword_id: str = Query(None, description="Boş bırakılırsa tüm aktif keyword'ler")
):
    """
    Manuel scrape tetikler.
    keyword_id verilirse sadece o keyword, yoksa tüm aktifler.
    """
    if keyword_id:
        kw = supabase.table("keywords").select("*").eq("id", keyword_id).execute()
        if not kw.data:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Keyword bulunamadı")
        kw_verisi = kw.data[0]
        background_tasks.add_task(keyword_isle, kw_verisi["id"], kw_verisi["keyword"])
        return {"mesaj": f"'{kw_verisi['keyword']}' için scrape başlatıldı"}
    else:
        background_tasks.add_task(tumunu_tara)
        return {"mesaj": "Tüm aktif keyword'ler için scrape başlatıldı"}


@router.get("/scrape/loglar")
async def scrape_loglari(limit: int = Query(20, ge=1, le=100)):
    """
    Son N scrape işleminin loglarını döner.
    """
    yanit = (
        supabase.table("scrape_loglari")
        .select("*")
        .order("baslama_zamani", desc=True)
        .limit(limit)
        .execute()
    )
    return yanit.data or []
