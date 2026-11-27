"""
scrapers/etsy_arama.py — Etsy arama sayfası scraper'ı
Keyword bazlı arama sonuçlarından listing verilerini çeker.
Etsy'nin public arama sayfasını parse eder (login gerektirmez).
"""
import httpx
import asyncio
import random
import logging
import re
from datetime import date
from typing import Optional
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from config import ayarlar

logger = logging.getLogger(__name__)

# User-Agent rotasyonu için
ua = UserAgent()

# Etsy arama URL şablonu
ETSY_ARAMA_URL = "https://www.etsy.com/search"
ETSY_API_URL = "https://openapi.etsy.com/v3/application/listings/active"


async def _etsy_api_ara(keyword: str, sayfa: int = 1, limit: int = 25) -> list[dict]:
    """Etsy resmi OpenAPI v3 kullanarak ürünleri çeker."""
    if not ayarlar.etsy_api_key:
        return []

    headers = {"x-api-key": ayarlar.etsy_api_key}
    params = {
        "keywords": keyword,
        "limit": limit,
        "offset": (sayfa - 1) * limit,
        "sort_on": "score"
    }

    async with httpx.AsyncClient(timeout=15.0) as istemci:
        try:
            logger.info(f"Etsy resmi API çağrılıyor: '{keyword}', sayfa {sayfa}")
            res = await istemci.get(ETSY_API_URL, headers=headers, params=params)
            res.raise_for_status()
            data = res.json()
            results = data.get("results", [])

            listinglar = []
            for item in results:
                p = item.get("price", {})
                amount = round(p.get("amount", 0) / p.get("divisor", 100), 2) if p.get("divisor") else None
                curr = p.get("currency_code", "USD")
                favs = item.get("num_favorers", 0)
                views = item.get("views", 0)

                listinglar.append({
                    "etsy_listing_id": item["listing_id"],
                    "baslik": (item.get("title") or "")[:500],
                    "fiyat": amount,
                    "para_birimi": curr,
                    "magaza_adi": f"Shop #{item.get('shop_id')}",
                    "star_seller_mi": False,
                    "listing_url": (item.get("url") or f"https://www.etsy.com/listing/{item['listing_id']}")[:500],
                    "resim_url": None,
                    "etiketler": item.get("tags") or [],
                    "favori_sayisi": favs,
                    "yorum_sayisi": int(views * 0.05),
                    "satis_tahmini": max(1, int(favs * 1.5))
                })
            logger.info(f"Etsy API başarılı: {len(listinglar)} ürün bulundu.")
            return listinglar
        except Exception as e:
            logger.error(f"Etsy resmi API hatası: {e}")
            return []


def _rastgele_basliklar() -> dict:
    """Her request için farklı header'lar — bot tespitini azaltır."""
    return {
        "User-Agent": ua.random,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }


def _fiyat_coz(fiyat_metni: Optional[str]) -> Optional[float]:
    """
    '$29.99', '€15,00', '29.99 USD' gibi fiyat string'lerini float'a çevirir.
    """
    if not fiyat_metni:
        return None
    temiz = re.sub(r"[^\d.,]", "", fiyat_metni)
    # Avrupa formatı: 29,99 → 29.99
    if "," in temiz and "." not in temiz:
        temiz = temiz.replace(",", ".")
    elif "," in temiz and "." in temiz:
        # 1.299,99 → 1299.99
        temiz = temiz.replace(".", "").replace(",", ".")
    try:
        return float(temiz)
    except ValueError:
        return None


def _listing_parse_et(kart: BeautifulSoup) -> Optional[dict]:
    """
    Tek bir Etsy listing kartını parse eder.
    Veri bulunamazsa None döner.
    """
    try:
        # Listing URL ve ID
        link = kart.select_one("a[href*='/listing/']")
        if not link:
            return None

        href = link.get("href", "")
        listing_id_eslemi = re.search(r"/listing/(\d+)/", href)
        if not listing_id_eslemi:
            return None

        listing_id = int(listing_id_eslemi.group(1))
        listing_url = href.split("?")[0]  # query string'i at

        # Başlık
        baslik_elem = kart.select_one("h3") or kart.select_one("[data-listing-id] h2")
        baslik = baslik_elem.get_text(strip=True) if baslik_elem else "Bilinmiyor"

        # Fiyat — birden fazla fiyat elementi olabilir (indirimli fiyat)
        fiyat_elem = kart.select_one("[data-currency-value]") or kart.select_one(".currency-value")
        fiyat = None
        if fiyat_elem:
            fiyat = _fiyat_coz(fiyat_elem.get("data-currency-value") or fiyat_elem.get_text())

        # Mağaza adı
        magaza_elem = kart.select_one("[data-shop-name]") or kart.select_one(".shop-name")
        magaza_adi = magaza_elem.get_text(strip=True) if magaza_elem else "Bilinmiyor"

        # Star Seller rozeti
        star_seller = bool(kart.select_one("[data-star-seller]") or kart.select_one(".star-seller-badge"))

        # Resim URL
        resim_elem = kart.select_one("img[data-src]") or kart.select_one("img[src]")
        resim_url = None
        if resim_elem:
            resim_url = resim_elem.get("data-src") or resim_elem.get("src")

        return {
            "etsy_listing_id": listing_id,
            "baslik": baslik[:500],
            "fiyat": fiyat,
            "para_birimi": "USD",
            "magaza_adi": magaza_adi[:200],
            "star_seller_mi": star_seller,
            "listing_url": listing_url[:500],
            "resim_url": resim_url[:500] if resim_url else None
        }

    except Exception as e:
        logger.debug(f"Listing parse hatası: {e}")
        return None


async def etsy_ara(keyword: str, sayfa: int = 1) -> list[dict]:
    """
    Etsy arama sonuçlarından listing verilerini çeker.
    Öncelikle resmi Etsy OpenAPI v3'ü dener; başarısız olursa HTML kazımaya düşer.
    """
    # 1. Resmi Etsy API dene (DataDome engelsiz)
    if ayarlar.etsy_api_key:
        api_sonuclar = await _etsy_api_ara(keyword, sayfa=sayfa)
        if api_sonuclar:
            return api_sonuclar

    # 2. HTML Kazıma Fallback
    params = {
        "q": keyword,
        "page": sayfa,
        "ref": "pagination"
    }

    async with httpx.AsyncClient(
        headers=_rastgele_basliklar(),
        follow_redirects=True,
        timeout=30
    ) as istemci:
        try:
            logger.info(f"Etsy arama: '{keyword}' sayfa {sayfa}")
            yanit = await istemci.get(ETSY_ARAMA_URL, params=params)

            if yanit.status_code == 429:
                logger.warning(f"Rate limit! '{keyword}' için bekleniyor...")
                await asyncio.sleep(60)  # 1 dakika bekle
                return []

            yanit.raise_for_status()

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP hatası: {e.response.status_code} — '{keyword}'")
            return []
        except httpx.RequestError as e:
            logger.error(f"İstek hatası: {e} — '{keyword}'")
            return []

    soup = BeautifulSoup(yanit.text, "lxml")

    # Listing kartlarını bul — Etsy'nin class'ları sık değiştiğinden
    # birden fazla selector dener
    kartlar = (
        soup.select("div.js-merch-stash-check-listing") or
        soup.select("[data-listing-id]") or
        soup.select("li.wt-list-unstyled > div") or
        []
    )

    logger.info(f"'{keyword}' sayfa {sayfa}: {len(kartlar)} kart bulundu")

    listinglar = []
    for kart in kartlar:
        veri = _listing_parse_et(kart)
        if veri:
            listinglar.append(veri)

    return listinglar


async def keyword_tam_scrape(keyword: str) -> dict:
    """
    Bir keyword için tüm sayfaları scrape eder (max SCRAPE_SAYFA_LIMITI).
    
    Returns:
        {
            "listinglar": [...],
            "toplam_cekildi": int,
            "hatalar": []
        }
    """
    tum_listinglar = []
    hatalar = []

    for sayfa in range(1, ayarlar.scrape_sayfa_limiti + 1):
        # Sayfalar arası rastgele bekleme (rate limiting için)
        if sayfa > 1:
            bekleme = random.uniform(
                ayarlar.scrape_bekleme_min,
                ayarlar.scrape_bekleme_max
            )
            logger.debug(f"Bekleniyor: {bekleme:.1f}s")
            await asyncio.sleep(bekleme)

        listinglar = await etsy_ara(keyword, sayfa=sayfa)

        if not listinglar:
            logger.info(f"'{keyword}' sayfa {sayfa}: veri yok, duruyorum")
            break

        tum_listinglar.extend(listinglar)
        logger.info(f"'{keyword}' sayfa {sayfa}: {len(listinglar)} listing eklendi, toplam: {len(tum_listinglar)}")

        # Eğer gelen ürün sayısı sayfa limitinden (25) azsa son sayfadayız demektir
        if len(listinglar) < 25:
            logger.info(f"'{keyword}': Son sayfaya ulaşıldı ({len(listinglar)} < 25).")
            break

    # Tekrar eden listing ID'lerini kaldır (sayfa geçişlerinde overlap olabilir)
    goruldu = set()
    tekrarsiz = []
    for listing in tum_listinglar:
        lid = listing["etsy_listing_id"]
        if lid not in goruldu:
            goruldu.add(lid)
            tekrarsiz.append(listing)

    return {
        "listinglar": tekrarsiz,
        "toplam_cekildi": len(tekrarsiz),
        "hatalar": hatalar
    }
