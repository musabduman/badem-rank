"""
services/analitik_service.py — İstatistik ve analiz hesaplamaları
Ham veritabanı verilerini anlamlı metriklere dönüştürür.
"""
import logging
from typing import List, Optional
from datetime import date, timedelta
from database import supabase

logger = logging.getLogger(__name__)


async def etiket_analizi_hesapla(keyword_id: str) -> List[dict]:
    """
    Belirli bir keyword'ün listing'lerindeki etiket performansını hesaplar.
    
    Mantık:
    - Her etiketin kaç listing'de geçtiğini say
    - O etiketli listing'lerin ortalama satış tahmini, fiyat ve favori sayısını hesapla
    - Star seller oranını hesapla
    - Sonuçları ortalama satışa göre sırala
    """
    # Keyword'ün tüm listing'lerini çek
    yanit = (
        supabase.table("listinglar")
        .select("etiketler, satis_tahmini, fiyat, favori_sayisi, star_seller_mi")
        .eq("keyword_id", keyword_id)
        .execute()
    )

    if not yanit.data:
        return []

    # Etiket bazında gruplama
    etiket_verileri: dict[str, dict] = {}

    for listing in yanit.data:
        etiketler = listing.get("etiketler") or []
        for etiket in etiketler:
            if etiket not in etiket_verileri:
                etiket_verileri[etiket] = {
                    "etiket": etiket,
                    "kullanim_sayisi": 0,
                    "toplam_satis": 0,
                    "toplam_fiyat": 0,
                    "toplam_favori": 0,
                    "star_seller_sayisi": 0,
                    "fiyatli_listing_sayisi": 0
                }

            v = etiket_verileri[etiket]
            v["kullanim_sayisi"] += 1
            v["toplam_satis"] += listing.get("satis_tahmini") or 0
            v["toplam_favori"] += listing.get("favori_sayisi") or 0

            if listing.get("star_seller_mi"):
                v["star_seller_sayisi"] += 1

            if listing.get("fiyat"):
                v["toplam_fiyat"] += listing["fiyat"]
                v["fiyatli_listing_sayisi"] += 1

    # Ortalama hesapla ve sırala
    sonuclar = []
    for v in etiket_verileri.values():
        sayi = v["kullanim_sayisi"]
        fiyatli = v["fiyatli_listing_sayisi"]
        sonuclar.append({
            "etiket": v["etiket"],
            "kullanim_sayisi": sayi,
            "ort_satis_tahmini": round(v["toplam_satis"] / sayi, 1) if sayi > 0 else 0,
            "ort_fiyat": round(v["toplam_fiyat"] / fiyatli, 2) if fiyatli > 0 else 0,
            "toplam_favori": v["toplam_favori"],
            "star_seller_orani": round(v["star_seller_sayisi"] / sayi, 3) if sayi > 0 else 0
        })

    # Ortalama satışa göre azalan sırala
    sonuclar.sort(key=lambda x: x["ort_satis_tahmini"], reverse=True)
    return sonuclar


async def fiyat_analizi_hesapla(keyword_id: str) -> dict:
    """
    Belirli keyword için fiyat dağılımı istatistiklerini döner.
    """
    yanit = (
        supabase.table("listinglar")
        .select("fiyat")
        .eq("keyword_id", keyword_id)
        .not_.is_("fiyat", "null")
        .execute()
    )

    if not yanit.data:
        return {}

    fiyatlar = sorted([r["fiyat"] for r in yanit.data if r.get("fiyat")])
    sayi = len(fiyatlar)

    if sayi == 0:
        return {}

    # Yüzdelik dilimler
    def yuzdelik(dizi, oran):
        index = int(len(dizi) * oran)
        return dizi[min(index, len(dizi) - 1)]

    return {
        "min": fiyatlar[0],
        "max": fiyatlar[-1],
        "medyan": yuzdelik(fiyatlar, 0.5),
        "p25": yuzdelik(fiyatlar, 0.25),
        "p75": yuzdelik(fiyatlar, 0.75),
        "ortalama": round(sum(fiyatlar) / sayi, 2),
        "toplam_listing": sayi,
        # Fiyat segmentleri
        "segment_0_25": len([f for f in fiyatlar if f <= 25]),
        "segment_25_50": len([f for f in fiyatlar if 25 < f <= 50]),
        "segment_50_100": len([f for f in fiyatlar if 50 < f <= 100]),
        "segment_100_plus": len([f for f in fiyatlar if f > 100])
    }


async def rekabet_skoru_hesapla(listing_sayisi: int, star_seller_sayisi: int) -> int:
    """
    1-100 arası rekabet skoru üretir.
    
    Mantık:
    - Yüksek listing sayısı → yüksek rekabet
    - Yüksek star seller oranı → daha kaliteli rakipler
    - Skor 100 = çok yüksek rekabet, 1 = çok düşük rekabet
    """
    if listing_sayisi == 0:
        return 0

    # Listing sayısı skoru (0-60 arası)
    if listing_sayisi < 1000:
        listing_skoru = listing_sayisi / 1000 * 40
    elif listing_sayisi < 10000:
        listing_skoru = 40 + (listing_sayisi - 1000) / 9000 * 20
    else:
        listing_skoru = 60

    # Star seller skoru (0-40 arası)
    star_orani = min(star_seller_sayisi / 48, 1.0)  # ilk sayfada max 48 listing
    star_skoru = star_orani * 40

    return min(100, int(listing_skoru + star_skoru))


async def gunluk_delta_hesapla(listing_id: str, bugun: date) -> dict:
    """
    Bir listing için dünle bugünkü değerlerin farkını hesaplar.
    Veritabanına yazılacak delta değerlerini döner.
    """
    dun = bugun - timedelta(days=1)

    yanit = (
        supabase.table("listing_gunluk_anliklari")
        .select("*")
        .eq("listing_id", listing_id)
        .in_("tarih", [str(bugun), str(dun)])
        .order("tarih", desc=True)
        .execute()
    )

    anliklari = {r["tarih"]: r for r in (yanit.data or [])}
    bugunki = anliklari.get(str(bugun), {})
    dunku = anliklari.get(str(dun), {})

    def delta(alan):
        b = bugunki.get(alan, 0) or 0
        d = dunku.get(alan, 0) or 0
        return max(0, b - d)  # negatif delta anlamsız (scrape hatası olabilir)

    return {
        "gunluk_satis_degisim": delta("satis_tahmini"),
        "gunluk_favori_degisim": delta("favori_sayisi"),
        "gunluk_yorum_degisim": delta("yorum_sayisi")
    }
