"""
routers/magazalar.py — Mağaza takibi API endpoint'leri

GET    /api/magazalar                         → takip edilen mağazalar listesi (istatistiklerle)
POST   /api/magazalar/ara                     → alan/keyword veya tek mağaza adına göre Etsy'de ara
GET    /api/magazalar/etsy/{shop_id}/listinglar → mağazanın aktif ürünlerini önizle (takipsiz de çalışır)
POST   /api/magazalar/ekle                    → mağazayı takibe al ve ürünlerini kaydet
DELETE /api/magazalar/{magaza_id}             → takibi bırak
GET    /api/magazalar/{magaza_id}/listinglar  → mağazanın DB'deki ürünleri
PATCH  /api/magaza-listingleri/{listing_id}   → tekil ürün takip_aktif toggle
"""
import asyncio
import logging
from datetime import date
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from supabase import Client

from config import ayarlar
from database import supabase_al

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/magazalar", tags=["magazalar"])
listing_router = APIRouter(prefix="/api/magaza-listingleri", tags=["magazalar"])


# ─── Yardımcı: Etsy API ─────────────────────────────────────────────────────

def _etsy_headers() -> dict:
    if not ayarlar.etsy_api_key:
        raise HTTPException(status_code=503, detail="Etsy API anahtarı yapılandırılmamış")
    return {"x-api-key": ayarlar.etsy_api_key}


async def _etsy_get(
    url: str,
    params: Optional[dict] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> dict:
    """Etsy API'ye GET isteği atar (429 rate-limit durumunda kısa bekleyip 1 kez tekrar dener)."""
    headers = _etsy_headers()

    async def _do(c: httpx.AsyncClient) -> dict:
        r = await c.get(url, headers=headers, params=params or {})
        if r.status_code == 429:
            await asyncio.sleep(0.75)
            r = await c.get(url, headers=headers, params=params or {})
        r.raise_for_status()
        return r.json()

    if client is not None:
        return await _do(client)

    async with httpx.AsyncClient(timeout=20.0) as c:
        return await _do(c)


def _fiyat_hesapla(item: dict) -> tuple[Optional[float], str]:
    p = item.get("price") or {}
    divisor = p.get("divisor")
    fiyat = round(p.get("amount", 0) / divisor, 2) if divisor else None
    para_birimi = p.get("currency_code", "USD")
    return fiyat, para_birimi


def _etsy_listing_formatla(item: dict) -> dict:
    fiyat, para_birimi = _fiyat_hesapla(item)
    return {
        "etsy_listing_id": item["listing_id"],
        "baslik": (item.get("title") or "")[:500],
        "fiyat": fiyat,
        "para_birimi": para_birimi,
        "listing_type": item.get("listing_type"),
        "etiketler": item.get("tags") or [],
        "favori_sayisi": item.get("num_favorers", 0),
        "goruntuleme": item.get("views", 0),
        "stok_miktari": item.get("quantity", 0),
        "listing_url": item.get("url") or f"https://www.etsy.com/listing/{item['listing_id']}",
    }


def _yorum_puani_al(bilgi: dict) -> float:
    puan = bilgi.get("review_average")
    if puan is None:
        puan = bilgi.get("review_average_rating")
    return round(float(puan), 2) if puan else 0.0


# ─── Pydantic şemaları ──────────────────────────────────────────────────────

class MagazaEkleIstegi(BaseModel):
    shop_name: Optional[str] = None
    shop_id: Optional[int] = None
    arama_alani: Optional[str] = None
    haric_etsy_ids: list[int] = Field(default_factory=list)


class ListingTakipGuncelle(BaseModel):
    takip_aktif: bool


# ─── Etsy veri çekiciler ────────────────────────────────────────────────────

async def _magaza_bilgi_cek(
    shop_id: int,
    client: Optional[httpx.AsyncClient] = None,
) -> dict:
    try:
        return await _etsy_get(
            f"https://openapi.etsy.com/v3/application/shops/{shop_id}",
            client=client,
        )
    except Exception as e:
        logger.warning(f"Mağaza {shop_id} bilgisi çekilemedi: {e}")
        return {}


async def _magaza_listingleri_cek(
    shop_id: int,
    limit: int = 50,
    client: Optional[httpx.AsyncClient] = None,
) -> list[dict]:
    try:
        data = await _etsy_get(
            f"https://openapi.etsy.com/v3/application/shops/{shop_id}/listings/active",
            params={"limit": limit},
            client=client,
        )
        return data.get("results", [])
    except Exception as e:
        logger.warning(f"Mağaza {shop_id} listingleri çekilemedi: {e}")
        return []


async def magaza_urunlerini_senkronize_et(
    sb: Client,
    magaza_id: str,
    shop_id: int,
    haric_etsy_ids: Optional[list[int]] = None,
    mevcut_dislamalari_koru: bool = False,
    client: Optional[httpx.AsyncClient] = None,
) -> list[dict]:
    """
    Mağazanın aktif ürünlerini ve günlük istatistiğini Etsy'den çekip DB'ye kaydeder.
    - mevcut_dislamalari_koru=True ise kullanıcının daha önce takip_aktif=False yaptığı ürünler pasif kalır.
    - haric_etsy_ids verilirse o listing ID'ler takip_aktif=False olarak kaydedilir.
    """
    bilgi, listinglar = await asyncio.gather(
        _magaza_bilgi_cek(shop_id, client=client),
        _magaza_listingleri_cek(shop_id, limit=100, client=client),
    )

    haric_set: set[int] = set(haric_etsy_ids or [])
    if mevcut_dislamalari_koru:
        mevcut = (
            sb.table("magaza_listingleri")
            .select("etsy_listing_id, takip_aktif")
            .eq("magaza_id", magaza_id)
            .execute()
        )
        for row in mevcut.data or []:
            if row.get("takip_aktif") is False:
                haric_set.add(row["etsy_listing_id"])

    bugun = str(date.today())
    kaydedilen_listinglar: list[dict] = []

    if listinglar:
        kayitlar = []
        for item in listinglar:
            formatli = _etsy_listing_formatla(item)
            eid = formatli["etsy_listing_id"]
            kayitlar.append({
                "magaza_id": magaza_id,
                **formatli,
                "takip_aktif": eid not in haric_set,
                "son_guncellendi": bugun,
            })

        res = sb.table("magaza_listingleri").upsert(
            kayitlar,
            on_conflict="magaza_id,etsy_listing_id",
        ).execute()
        kaydedilen_listinglar = res.data or kayitlar
        logger.info(f"Mağaza {shop_id}: {len(kayitlar)} listing senkronize edildi")

    if bilgi:
        sb.table("magaza_anliklari").upsert(
            {
                "magaza_id": magaza_id,
                "tarih": bugun,
                "toplam_satis": bilgi.get("transaction_sold_count"),
                "yorum_sayisi": bilgi.get("review_count"),
                "yorum_puani": _yorum_puani_al(bilgi) or None,
                "aktif_listing_sayisi": len(listinglar),
            },
            on_conflict="magaza_id,tarih",
        ).execute()

    return kaydedilen_listinglar


# ─── Endpoint'ler ───────────────────────────────────────────────────────────

@router.get("")
async def magazalari_listele(sb: Client = Depends(supabase_al)):
    """Takip edilen mağazaları takip edilen ürün sayısı ve son satış istatistikleriyle döner."""
    r = (
        sb.table("magazalar")
        .select("*")
        .eq("takip_aktif", True)
        .order("guncellendi", desc=True)
        .execute()
    )
    magazalar = r.data or []
    if not magazalar:
        return []

    magaza_ids = [m["id"] for m in magazalar]

    # 2 toplu sorgu ile tüm mağazaların ürün sayısını ve son snapshot'ını al (N+1 yok)
    listing_rows = (
        sb.table("magaza_listingleri")
        .select("magaza_id, takip_aktif")
        .in_("magaza_id", magaza_ids)
        .execute()
    ).data or []

    anlik_rows = (
        sb.table("magaza_anliklari")
        .select("magaza_id, tarih, toplam_satis, yorum_sayisi, yorum_puani")
        .in_("magaza_id", magaza_ids)
        .order("tarih", desc=True)
        .execute()
    ).data or []

    takip_sayaci: dict[str, int] = {}
    toplam_sayaci: dict[str, int] = {}
    for row in listing_rows:
        mid = row["magaza_id"]
        toplam_sayaci[mid] = toplam_sayaci.get(mid, 0) + 1
        if row.get("takip_aktif", True):
            takip_sayaci[mid] = takip_sayaci.get(mid, 0) + 1

    son_anlik: dict[str, dict] = {}
    for row in anlik_rows:
        mid = row["magaza_id"]
        if mid not in son_anlik:
            son_anlik[mid] = row

    sonuc = []
    for m in magazalar:
        mid = m["id"]
        anlik = son_anlik.get(mid, {})
        sonuc.append({
            **m,
            "takip_edilen_urun_sayisi": takip_sayaci.get(mid, 0),
            "toplam_urun_sayisi": toplam_sayaci.get(mid, 0),
            "toplam_satis": anlik.get("toplam_satis"),
            "yorum_puani": anlik.get("yorum_puani"),
            "yorum_sayisi": anlik.get("yorum_sayisi"),
        })
    return sonuc


@router.post("/ara")
async def magaza_ara(
    keyword: str,
    tur: str = "alan",
    sb: Client = Depends(supabase_al),
):
    """
    Etsy'de arama yapar:
    - tur=alan   : keyword alanında en çok satan mağazaları bulur
    - tur=magaza : doğrudan mağaza adına göre arar
    """
    temiz_kw = keyword.strip()
    if not temiz_kw:
        raise HTTPException(status_code=400, detail="Arama metni boş olamaz")

    if tur == "magaza":
        return await _tek_magaza_ara(temiz_kw, sb)
    return await _alan_magaza_ara(temiz_kw, sb)


def _takip_haritasi_al(sb: Client, shop_ids: list[int]) -> dict[int, str]:
    """Verilen shop_id'lerden aktif takip edilenlerin {shop_id: magaza_id} haritasını döner."""
    if not shop_ids:
        return {}
    try:
        r = (
            sb.table("magazalar")
            .select("id, shop_id")
            .in_("shop_id", shop_ids)
            .eq("takip_aktif", True)
            .execute()
        )
        return {row["shop_id"]: row["id"] for row in (r.data or [])}
    except Exception:
        return {}


async def _tek_magaza_ara(shop_name: str, sb: Client) -> list[dict]:
    """Mağaza adına göre Etsy'de mağaza arar."""
    try:
        data = await _etsy_get(
            "https://openapi.etsy.com/v3/application/shops",
            params={"shop_name": shop_name},
        )
        results = data.get("results", [])
        takip_map = _takip_haritasi_al(sb, [s["shop_id"] for s in results if s.get("shop_id")])

        magazalar = []
        for s in results:
            sid = s["shop_id"]
            magaza_id = takip_map.get(sid)
            magazalar.append({
                "shop_id": sid,
                "shop_name": s["shop_name"],
                "toplam_satis": s.get("transaction_sold_count", 0),
                "yorum_sayisi": s.get("review_count", 0),
                "yorum_puani": _yorum_puani_al(s),
                "url": s.get("url") or f"https://www.etsy.com/shop/{s['shop_name']}",
                "takip_ediliyor": magaza_id is not None,
                "magaza_id": magaza_id,
            })
        return magazalar
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Mağaza arama hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _alan_magaza_ara(keyword: str, sb: Client) -> list[dict]:
    """
    Keyword alanındaki en iyi mağazaları bulur.
    Etsy 5 req/sn limitine uyarak paralel shop bilgisi çeker.
    """
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            data = await _etsy_get(
                "https://openapi.etsy.com/v3/application/listings/active",
                params={"keywords": keyword, "limit": 100, "sort_on": "score"},
                client=client,
            )
            results = data.get("results", [])

            shop_map: dict[int, int] = {}
            for item in results:
                sid = item.get("shop_id")
                if sid:
                    shop_map[sid] = shop_map.get(sid, 0) + 1

            top_shop_ids = sorted(shop_map, key=shop_map.__getitem__, reverse=True)[:12]
            if not top_shop_ids:
                return []

            # Etsy 5 req/sn limitine takılmamak için istekleri ~4 req/sn hızına yay
            async def fetch_one(idx: int, sid: int) -> tuple[int, dict]:
                if idx > 0:
                    await asyncio.sleep(idx * 0.25)
                return sid, await _magaza_bilgi_cek(sid, client=client)

            shop_infos = await asyncio.gather(
                *(fetch_one(idx, sid) for idx, sid in enumerate(top_shop_ids))
            )

        takip_map = _takip_haritasi_al(sb, top_shop_ids)

        magazalar = []
        for shop_id, bilgi in shop_infos:
            if not bilgi:
                continue
            magaza_id = takip_map.get(shop_id)
            sname = bilgi.get("shop_name", f"Shop #{shop_id}")
            magazalar.append({
                "shop_id": shop_id,
                "shop_name": sname,
                "toplam_satis": bilgi.get("transaction_sold_count", 0),
                "yorum_sayisi": bilgi.get("review_count", 0),
                "yorum_puani": _yorum_puani_al(bilgi),
                "url": bilgi.get("url") or f"https://www.etsy.com/shop/{sname}",
                "sonuc_sayisi": shop_map[shop_id],
                "takip_ediliyor": magaza_id is not None,
                "magaza_id": magaza_id,
            })

        magazalar.sort(key=lambda x: x["toplam_satis"], reverse=True)
        return magazalar

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Alan arama hatası '{keyword}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/etsy/{shop_id}/listinglar")
async def etsy_magaza_listing_onizleme(
    shop_id: int,
    sb: Client = Depends(supabase_al),
):
    """
    Mağaza takip edilsin ya da edilmesin ürünlerini listeler.
    Takip ediliyorsa ve DB'de ürünleri varsa DB'den; yoksa Etsy'den anlık çeker.
    """
    try:
        mevcut = (
            sb.table("magazalar")
            .select("id")
            .eq("shop_id", shop_id)
            .eq("takip_aktif", True)
            .execute()
        )
        if mevcut.data:
            magaza_id = mevcut.data[0]["id"]
            db_urunler = (
                sb.table("magaza_listingleri")
                .select("*")
                .eq("magaza_id", magaza_id)
                .order("favori_sayisi", desc=True)
                .execute()
            ).data or []
            if db_urunler:
                return [{**u, "kayitli": True} for u in db_urunler]
    except Exception as e:
        logger.warning(f"Mağaza önizleme DB kontrolü atlandı ({shop_id}): {e}")

    # DB'de henüz yoksa Etsy'den canlı çek
    raw_results = await _magaza_listingleri_cek(shop_id, limit=50)
    urunler = [
        {
            **_etsy_listing_formatla(item),
            "id": None,
            "takip_aktif": False,
            "kayitli": False,
        }
        for item in raw_results
    ]
    urunler.sort(key=lambda x: x["favori_sayisi"], reverse=True)
    return urunler


@router.post("/ekle")
async def magaza_ekle(
    istek: MagazaEkleIstegi,
    sb: Client = Depends(supabase_al),
):
    """
    Mağazayı takibe alır, tüm ürünlerini senkron şekilde kaydeder ve ürünleri döner.
    Böylece kullanıcı hemen ardından ürünlerden istediğini tikten çıkarabilir.
    """
    if not istek.shop_id and not istek.shop_name:
        raise HTTPException(status_code=400, detail="shop_name veya shop_id gerekli")

    shop_id = istek.shop_id
    shop_name = istek.shop_name

    if not shop_id and shop_name:
        try:
            data = await _etsy_get(
                "https://openapi.etsy.com/v3/application/shops",
                params={"shop_name": shop_name},
            )
            results = data.get("results", [])
            if not results:
                raise HTTPException(status_code=404, detail=f"'{shop_name}' mağazası bulunamadı")
            shop_id = results[0]["shop_id"]
            shop_name = results[0]["shop_name"]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    mevcut = sb.table("magazalar").select("id, shop_name").eq("shop_id", shop_id).execute()
    if mevcut.data:
        magaza_id = mevcut.data[0]["id"]
        shop_name = shop_name or mevcut.data[0].get("shop_name")
        sb.table("magazalar").update({
            "takip_aktif": True,
            "arama_alani": istek.arama_alani,
        }).eq("shop_id", shop_id).execute()
    else:
        yeni = sb.table("magazalar").insert({
            "shop_id": shop_id,
            "shop_name": shop_name or f"Shop #{shop_id}",
            "arama_alani": istek.arama_alani,
            "takip_aktif": True,
        }).execute()
        magaza_id = yeni.data[0]["id"]

    # Tüm ürünleri senkron olarak çek ve kaydet (kullanıcıya hemen dönebilmek için)
    kaydedilen_listinglar = await magaza_urunlerini_senkronize_et(
        sb=sb,
        magaza_id=magaza_id,
        shop_id=shop_id,
        haric_etsy_ids=istek.haric_etsy_ids,
        mevcut_dislamalari_koru=False,
    )

    return {
        "basarili": True,
        "magaza_id": magaza_id,
        "shop_id": shop_id,
        "shop_name": shop_name,
        "listinglar": kaydedilen_listinglar,
    }


@router.delete("/{magaza_id}")
async def magaza_takibi_birak(
    magaza_id: str,
    sb: Client = Depends(supabase_al),
):
    """Mağazayı takipten çıkarır (soft delete — geçmiş verileri silmez)."""
    r = (
        sb.table("magazalar")
        .update({"takip_aktif": False})
        .eq("id", magaza_id)
        .execute()
    )
    if not r.data:
        raise HTTPException(status_code=404, detail="Mağaza bulunamadı")
    return {"basarili": True}


@router.get("/{magaza_id}/listinglar")
async def magaza_listingleri_getir(
    magaza_id: str,
    sadece_takip: bool = False,
    sb: Client = Depends(supabase_al),
):
    """Mağazanın DB'deki ürünlerini döner."""
    q = (
        sb.table("magaza_listingleri")
        .select("*")
        .eq("magaza_id", magaza_id)
        .order("favori_sayisi", desc=True)
    )
    if sadece_takip:
        q = q.eq("takip_aktif", True)
    r = q.execute()
    return r.data or []


@listing_router.patch("/{listing_id}")
async def listing_takip_guncelle(
    listing_id: str,
    istek: ListingTakipGuncelle,
    sb: Client = Depends(supabase_al),
):
    """Tekil ürün takibini açar/kapatır."""
    r = (
        sb.table("magaza_listingleri")
        .update({"takip_aktif": istek.takip_aktif})
        .eq("id", listing_id)
        .execute()
    )
    if not r.data:
        raise HTTPException(status_code=404, detail="Listing bulunamadı")
    return {"basarili": True}
