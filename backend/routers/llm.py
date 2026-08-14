"""
routers/llm.py — LLM chat ve pazar raporu endpoint'leri
Sağ panel AI sohbeti ve LLM raporu üretimi burada yönetilir.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from database import supabase
from models.rapor import ChatIstek, ChatYaniti, RaporOlusturIstek, PazarRaporuYaniti
from services.llm_service import llm_yanit_stream, llm_yanit_al, pazar_raporu_olustur
from services.analitik_service import etiket_analizi_hesapla, fiyat_analizi_hesapla
from datetime import date
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/llm", tags=["LLM"])


@router.post("/chat")
async def llm_chat(istek: ChatIstek):
    """
    Ollama API ile streaming chat yanıtı döner.
    Frontend sağ paneli SSE (Server-Sent Events) ile dinler.
    
    Response: text/event-stream
    Her event: data: {"token": "..."}\n\n
    Son event: data: [DONE]\n\n
    """
    return StreamingResponse(
        llm_yanit_stream(
            mesaj=istek.mesaj,
            gecmis=istek.gecmis,
            keyword_baglami=istek.keyword_baglami
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"  # Nginx buffering'i kapat
        }
    )


@router.post("/rapor-olustur", response_model=PazarRaporuYaniti)
async def rapor_olustur(istek: RaporOlusturIstek):
    """
    Belirli keyword için LLM pazar raporu üretir ve önbelleğe alır.
    Aynı keyword + tarih + tip için önbellekte varsa direkt döner (yeniden_olustur=False ise).
    """
    bugun = date.today().isoformat()

    # Önbellek kontrolü
    if not istek.yeniden_olustur:
        onbellek = (
            supabase.table("pazar_raporlari")
            .select("*")
            .eq("keyword_id", str(istek.keyword_id))
            .eq("rapor_tarihi", bugun)
            .eq("rapor_tipi", istek.rapor_tipi)
            .execute()
        )
        if onbellek.data:
            logger.info("Önbellekten rapor döndürülüyor")
            return onbellek.data[0]

    # Keyword bilgisi
    kw_yanit = supabase.table("keywords").select("keyword").eq("id", str(istek.keyword_id)).execute()
    if not kw_yanit.data:
        raise HTTPException(status_code=404, detail="Keyword bulunamadı")

    keyword_metni = kw_yanit.data[0]["keyword"]

    # Analiz verilerini hazırla
    try:
        etiket_verisi = await etiket_analizi_hesapla(str(istek.keyword_id))
        fiyat_verisi = await fiyat_analizi_hesapla(str(istek.keyword_id))
    except Exception as e:
        logger.error(f"Analiz verisi hazırlama hatası: {e}")
        etiket_verisi = []
        fiyat_verisi = {}

    # LLM ile rapor üret
    try:
        rapor_metni = await pazar_raporu_olustur(
            keyword=keyword_metni,
            etiket_verileri=etiket_verisi,
            fiyat_verileri=fiyat_verisi,
            rapor_tipi=istek.rapor_tipi
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # Veritabanına kaydet
    from config import ayarlar
    kayit_verisi = {
        "keyword_id": str(istek.keyword_id),
        "rapor_tarihi": bugun,
        "rapor_tipi": istek.rapor_tipi,
        "icerik": rapor_metni,
        "kullanilan_model": ayarlar.ollama_model
    }

    yanit = (
        supabase.table("pazar_raporlari")
        .upsert(kayit_verisi, on_conflict="keyword_id,rapor_tarihi,rapor_tipi")
        .execute()
    )

    if not yanit.data:
        raise HTTPException(status_code=500, detail="Rapor kaydedilemedi")

    return yanit.data[0]


@router.get("/raporlar/{keyword_id}", response_model=list[PazarRaporuYaniti])
async def rapor_gecmisi(keyword_id: str, limit: int = 10):
    """
    Keyword'ün geçmiş raporlarını listeler.
    """
    yanit = (
        supabase.table("pazar_raporlari")
        .select("*")
        .eq("keyword_id", keyword_id)
        .order("rapor_tarihi", desc=True)
        .limit(limit)
        .execute()
    )
    return yanit.data or []
