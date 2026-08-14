"""
services/llm_service.py — Ollama API ile iletişim
Ollama'nın OpenAI-uyumlu API endpoint'ini kullanır (/api/chat).
"""
import httpx
import logging
import json
from typing import AsyncGenerator, List, Optional
from config import ayarlar
from models.rapor import ChatMesaji

logger = logging.getLogger(__name__)


def _sistem_mesaji_olustur(keyword_baglami: Optional[str] = None) -> str:
    """
    LLM için sistem mesajı oluşturur.
    Keyword bağlamı varsa veriye göre yorum yapmasını sağlar.
    """
    temel = (
        "Sen bir Etsy pazar analisti asistanısın. "
        "Kullanıcıya Etsy'deki ürün ve keyword performansı hakkında "
        "Türkçe, net ve pratik tavsiyeler veriyorsun. "
        "Cevapların kısa ve aksiyona yönelik olsun. "
        "Sayısal veriler paylaşıldığında bunları yorumla."
    )
    if keyword_baglami:
        temel += f'\n\nŞu an kullanıcı "{keyword_baglami}" keyword\'ünü analiz ediyor.'
    return temel


def _ollama_mesajlari_hazirla(
    sistem: str,
    gecmis: List[ChatMesaji],
    yeni_mesaj: str
) -> List[dict]:
    """
    Ollama /api/chat formatı için mesaj listesi oluşturur.
    Rol isimleri: system | user | assistant
    """
    mesajlar = [{"role": "system", "content": sistem}]

    for m in gecmis:
        # Türkçe rol isimlerini Ollama formatına çevir
        rol_map = {"kullanici": "user", "asistan": "assistant", "sistem": "system"}
        ollama_rol = rol_map.get(m.rol, m.rol)
        mesajlar.append({"role": ollama_rol, "content": m.icerik})

    mesajlar.append({"role": "user", "content": yeni_mesaj})
    return mesajlar


async def llm_yanit_al(
    mesaj: str,
    gecmis: List[ChatMesaji],
    keyword_baglami: Optional[str] = None
) -> str:
    """
    Ollama API'den tek seferlik yanıt alır (streaming değil).
    Raporlar ve önbellek için kullanılır.
    """
    sistem = _sistem_mesaji_olustur(keyword_baglami)
    mesajlar = _ollama_mesajlari_hazirla(sistem, gecmis, mesaj)

    url = f"{ayarlar.ollama_api_url}/api/chat"

    async with httpx.AsyncClient(timeout=120) as istemci:
        try:
            yanit = await istemci.post(
                url,
                json={
                    "model": ayarlar.ollama_model,
                    "messages": mesajlar,
                    "stream": False
                }
            )
            yanit.raise_for_status()
            veri = yanit.json()
            return veri["message"]["content"]

        except httpx.TimeoutException:
            logger.error("Ollama API zaman aşımına uğradı")
            raise RuntimeError("LLM yanıt vermedi (zaman aşımı). Lütfen tekrar deneyin.")
        except httpx.HTTPStatusError as e:
            logger.error(f"Ollama API hatası: {e.response.status_code}")
            raise RuntimeError(f"LLM API hatası: {e.response.status_code}")
        except KeyError:
            logger.error("Ollama API beklenmedik yanıt formatı döndürdü")
            raise RuntimeError("LLM yanıt formatı beklenmedik. Model adını kontrol et.")


async def llm_yanit_stream(
    mesaj: str,
    gecmis: List[ChatMesaji],
    keyword_baglami: Optional[str] = None
) -> AsyncGenerator[str, None]:
    """
    Ollama API'den streaming yanıt üretir.
    Frontend'deki AI chat paneli için Server-Sent Events ile kullanılır.
    
    Her yield: 'data: {"token": "..."}\n\n' formatında SSE chunk'ı döner.
    """
    sistem = _sistem_mesaji_olustur(keyword_baglami)
    mesajlar = _ollama_mesajlari_hazirla(sistem, gecmis, mesaj)

    url = f"{ayarlar.ollama_api_url}/api/chat"

    async with httpx.AsyncClient(timeout=180) as istemci:
        try:
            async with istemci.stream(
                "POST",
                url,
                json={
                    "model": ayarlar.ollama_model,
                    "messages": mesajlar,
                    "stream": True
                }
            ) as yanit:
                yanit.raise_for_status()
                async for satir in yanit.aiter_lines():
                    if not satir.strip():
                        continue
                    try:
                        chunk = json.loads(satir)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            # SSE formatı
                            yield f"data: {json.dumps({'token': token})}\n\n"
                        if chunk.get("done"):
                            yield "data: [DONE]\n\n"
                            break
                    except json.JSONDecodeError:
                        continue

        except httpx.TimeoutException:
            yield f"data: {json.dumps({'hata': 'Zaman aşımı'})}\n\n"
        except httpx.HTTPStatusError as e:
            yield f"data: {json.dumps({'hata': f'LLM hatası: {e.response.status_code}'})}\n\n"


async def pazar_raporu_olustur(
    keyword: str,
    etiket_verileri: list,
    fiyat_verileri: dict,
    rapor_tipi: str = "gunluk_ozet"
) -> str:
    """
    Pazar verilerini LLM'e göndererek analiz raporu üretir.
    Sonuç veritabanında önbelleğe alınır.
    """
    rapor_sablonlari = {
        "gunluk_ozet": (
            f'"{keyword}" keyword\'ü için bugünkü Etsy pazar özeti:\n\n'
            f"Fiyat bilgileri: {json.dumps(fiyat_verileri, ensure_ascii=False)}\n"
            f"Etiket performansı (ilk 10): {json.dumps(etiket_verileri[:10], ensure_ascii=False)}\n\n"
            "Bu verilere göre kısa bir pazar özeti yaz. "
            "Öne çıkan etiketleri, fiyat aralığını ve rekabet durumunu yorumla. "
            "Maksimum 3 paragraf."
        ),
        "etiket_analizi": (
            f'"{keyword}" için etiket (tag) analizi:\n\n'
            f"Etiket verileri: {json.dumps(etiket_verileri, ensure_ascii=False)}\n\n"
            "Hangi etiketler daha iyi performans gösteriyor? "
            "Satıcılara etiket stratejisi konusunda 3-5 maddelik tavsiye ver."
        ),
        "fiyat_analizi": (
            f'"{keyword}" için fiyat analizi:\n\n'
            f"Fiyat dağılımı: {json.dumps(fiyat_verileri, ensure_ascii=False)}\n\n"
            "Fiyatlandırma stratejisi konusunda pratik tavsiyeler ver. "
            "Hangi fiyat segmentinde daha az rekabet var? Maksimum 2 paragraf."
        )
    }

    prompt = rapor_sablonlari.get(rapor_tipi, rapor_sablonlari["gunluk_ozet"])
    return await llm_yanit_al(prompt, gecmis=[], keyword_baglami=keyword)
