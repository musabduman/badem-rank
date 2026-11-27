import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from main import app
from database import supabase_al

client = TestClient(app)


def _mock_sb():
    """Zincirlenebilir Supabase mock client'ı oluşturur."""
    sb = MagicMock()
    return sb


def test_magaza_etsy_listing_onizleme_takipsiz():
    """Takip edilmeyen mağazanın ürünleri Etsy'den önizlenebilmeli."""
    sb = _mock_sb()
    # Mağaza DB'de yok
    sb.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []

    app.dependency_overrides[supabase_al] = lambda: sb
    try:
        etsy_payload = {
            "results": [
                {
                    "listing_id": 101,
                    "title": "Crochet Bag PDF",
                    "price": {"amount": 599, "divisor": 100, "currency_code": "USD"},
                    "tags": ["crochet", "bag"],
                    "num_favorers": 42,
                    "views": 300,
                    "quantity": 99,
                    "url": "https://www.etsy.com/listing/101/crochet-bag",
                }
            ]
        }
        with patch("routers.magazalar._etsy_get", new=AsyncMock(return_value=etsy_payload)) as mock_get:
            res = client.get("/api/magazalar/etsy/12345/listinglar")
            assert res.status_code == 200
            data = res.json()
            assert len(data) == 1
            assert data[0]["etsy_listing_id"] == 101
            assert data[0]["fiyat"] == 5.99
            assert data[0]["takip_aktif"] is False
            assert data[0]["kayitli"] is False
            # includes=tags gibi geçersiz parametre gönderilmemeli
            _, kwargs = mock_get.call_args
            params = kwargs.get("params") or (mock_get.call_args.args[1] if len(mock_get.call_args.args) > 1 else {})
            assert "includes" not in (params or {})
    finally:
        app.dependency_overrides.clear()


def test_alan_magaza_ara_dogru_puan_ve_siralama():
    """Alan araması review_average alanını okumalı ve satışa göre sıralamalı."""
    sb = _mock_sb()
    sb.table.return_value.select.return_value.in_.return_value.eq.return_value.execute.return_value.data = [
        {"id": "mag-1", "shop_id": 222}
    ]
    app.dependency_overrides[supabase_al] = lambda: sb

    async def fake_etsy_get(url, params=None, client_arg=None, **kwargs):
        if "listings/active" in url:
            return {
                "results": [
                    {"shop_id": 111, "listing_id": 1},
                    {"shop_id": 222, "listing_id": 2},
                    {"shop_id": 222, "listing_id": 3},
                ]
            }
        if url.endswith("/shops/111"):
            return {"shop_id": 111, "shop_name": "LowSales", "transaction_sold_count": 50, "review_count": 10, "review_average": 4.7}
        if url.endswith("/shops/222"):
            return {"shop_id": 222, "shop_name": "TopShop", "transaction_sold_count": 1706, "review_count": 400, "review_average": 4.9}
        return {}

    try:
        with patch("routers.magazalar._etsy_get", side_effect=fake_etsy_get):
            res = client.post("/api/magazalar/ara?keyword=crochet+hat&tur=alan")
            assert res.status_code == 200
            data = res.json()
            assert len(data) == 2
            assert data[0]["shop_name"] == "TopShop"
            assert data[0]["yorum_puani"] == 4.9
            assert data[0]["takip_ediliyor"] is True
            assert data[0]["magaza_id"] == "mag-1"
            assert data[1]["shop_name"] == "LowSales"
            assert data[1]["takip_ediliyor"] is False
    finally:
        app.dependency_overrides.clear()


def test_magaza_ekle_urunleri_senkron_kaydeder_ve_doner():
    """Mağaza eklendiğinde ürünleri hemen kaydedip yanıt içinde dönmeli."""
    sb = _mock_sb()
    # Mevcut mağaza yok
    sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    # Insert yeni mağaza
    sb.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": "uuid-magaza-1", "shop_id": 555, "shop_name": "CrochetByNua"}
    ]
    # Upsert listingler
    saved_rows = [
        {
            "id": "list-uuid-1",
            "magaza_id": "uuid-magaza-1",
            "etsy_listing_id": 9001,
            "baslik": "Hat Pattern",
            "fiyat": 6.5,
            "etiketler": ["crochet"],
            "favori_sayisi": 15,
            "takip_aktif": True,
        }
    ]
    sb.table.return_value.upsert.return_value.execute.return_value.data = saved_rows

    app.dependency_overrides[supabase_al] = lambda: sb

    async def fake_etsy_get(url, params=None, **kwargs):
        if "/listings/active" in url:
            return {
                "results": [
                    {
                        "listing_id": 9001,
                        "title": "Hat Pattern",
                        "price": {"amount": 650, "divisor": 100, "currency_code": "USD"},
                        "tags": ["crochet"],
                        "num_favorers": 15,
                        "views": 100,
                        "quantity": 10,
                        "url": "https://www.etsy.com/listing/9001",
                    }
                ]
            }
        return {"shop_id": 555, "shop_name": "CrochetByNua", "transaction_sold_count": 1200, "review_count": 300, "review_average": 4.85}

    try:
        with patch("routers.magazalar._etsy_get", side_effect=fake_etsy_get):
            res = client.post(
                "/api/magazalar/ekle",
                json={"shop_id": 555, "shop_name": "CrochetByNua", "arama_alani": "crochet hat"},
            )
            assert res.status_code == 200
            body = res.json()
            assert body["basarili"] is True
            assert body["magaza_id"] == "uuid-magaza-1"
            assert len(body["listinglar"]) == 1
            assert body["listinglar"][0]["id"] == "list-uuid-1"
    finally:
        app.dependency_overrides.clear()


def test_magazalari_listele_zenginlestirilmis_istatistik_doner():
    """Dashboard mağaza listesi takip edilen ürün sayısı ve son satışı dönmeli."""
    sb = _mock_sb()

    def table_side_effect(name):
        t = MagicMock()
        if name == "magazalar":
            t.select.return_value.eq.return_value.order.return_value.execute.return_value.data = [
                {"id": "m1", "shop_id": 555, "shop_name": "CrochetByNua", "arama_alani": "crochet", "takip_aktif": True}
            ]
        elif name == "magaza_listingleri":
            t.select.return_value.in_.return_value.execute.return_value.data = [
                {"magaza_id": "m1", "takip_aktif": True},
                {"magaza_id": "m1", "takip_aktif": True},
                {"magaza_id": "m1", "takip_aktif": False},
            ]
        elif name == "magaza_anliklari":
            t.select.return_value.in_.return_value.order.return_value.execute.return_value.data = [
                {"magaza_id": "m1", "tarih": "2026-11-28", "toplam_satis": 1706, "yorum_puani": 4.8, "yorum_sayisi": 410}
            ]
        return t

    sb.table.side_effect = table_side_effect
    app.dependency_overrides[supabase_al] = lambda: sb
    try:
        res = client.get("/api/magazalar")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["takip_edilen_urun_sayisi"] == 2
        assert data[0]["toplam_urun_sayisi"] == 3
        assert data[0]["toplam_satis"] == 1706
        assert data[0]["yorum_puani"] == 4.8
    finally:
        app.dependency_overrides.clear()


def test_listing_takip_guncelle_ve_magaza_birak():
    """Tekil ürün checkbox'ı ve mağaza takipten çıkma doğru çalışmalı."""
    sb = _mock_sb()
    sb.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [{"id": "l1", "takip_aktif": False}]
    app.dependency_overrides[supabase_al] = lambda: sb
    try:
        r1 = client.patch("/api/magaza-listingleri/l1", json={"takip_aktif": False})
        assert r1.status_code == 200
        assert r1.json()["basarili"] is True

        r2 = client.delete("/api/magazalar/m1")
        assert r2.status_code == 200
        assert r2.json()["basarili"] is True
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_gunluk_magazalari_tara_kullanici_dislama_korur():
    """Günlük scrape takip edilen mağazaları güncellerken kullanıcının bıraktığı ürünleri tekrar aktif etmemeli."""
    from scrapers.calistir import magazalari_tara

    sb = _mock_sb()

    captured_upserts = {}

    def table_side_effect(name):
        t = MagicMock()
        if name == "magazalar":
            t.select.return_value.eq.return_value.execute.return_value.data = [
                {"id": "m1", "shop_id": 555, "shop_name": "CrochetByNua"}
            ]
        elif name == "magaza_listingleri":
            t.select.return_value.eq.return_value.execute.return_value.data = [
                {"etsy_listing_id": 1001, "takip_aktif": True},
                {"etsy_listing_id": 1002, "takip_aktif": False},  # Kullanıcı çıkardı
            ]
            def capture_upsert(rows, **kw):
                captured_upserts["listinglar"] = rows
                res = MagicMock()
                res.execute.return_value.data = rows
                return res
            t.upsert.side_effect = capture_upsert
        elif name == "magaza_anliklari":
            def capture_anlik(row, **kw):
                captured_upserts["anlik"] = row
                res = MagicMock()
                res.execute.return_value.data = [row]
                return res
            t.upsert.side_effect = capture_anlik
        return t

    sb.table.side_effect = table_side_effect

    mock_shop = {"shop_id": 555, "transaction_sold_count": 1710, "review_count": 412, "review_average": 4.8}
    mock_listings = [
        {"listing_id": 1001, "title": "A", "price": {"amount": 500, "divisor": 100, "currency_code": "USD"}, "tags": ["a"], "num_favorers": 10, "views": 50, "quantity": 5},
        {"listing_id": 1002, "title": "B", "price": {"amount": 700, "divisor": 100, "currency_code": "USD"}, "tags": ["b"], "num_favorers": 20, "views": 80, "quantity": 3},
        {"listing_id": 1003, "title": "C (Yeni)", "price": {"amount": 900, "divisor": 100, "currency_code": "USD"}, "tags": ["c"], "num_favorers": 1, "views": 5, "quantity": 10},
    ]

    with patch("scrapers.calistir.supabase", sb), \
         patch("scrapers.calistir.ayarlar") as mock_ayar, \
         patch("routers.magazalar._etsy_get", side_effect=[mock_shop, {"results": mock_listings}]):
        mock_ayar.etsy_api_key = "test:secret"
        await magazalari_tara()

    by_id = {r["etsy_listing_id"]: r for r in captured_upserts["listinglar"]}
    assert by_id[1001]["takip_aktif"] is True
    assert by_id[1002]["takip_aktif"] is False
    assert by_id[1003]["takip_aktif"] is True
    assert captured_upserts["anlik"]["toplam_satis"] == 1710


@pytest.mark.asyncio
async def test_magaza_listing_gunluk_satis_deltasi_ve_restock():
    """
    Stok düşüşü kadar gunluk_satis hesaplanmalı; restock (stok artışı) durumunda 0 olmalı.
    İlk kez görülen üründe delta 0 kaydedilmeli.
    """
    from routers.magazalar import magaza_urunlerini_senkronize_et

    sb = _mock_sb()
    captured = {}

    def table_side_effect(name):
        t = MagicMock()
        if name == "magaza_listingleri":
            def upsert_listings(rows, **kw):
                res = MagicMock()
                # DB UUID atanmış gibi döndür
                out = []
                for idx, r in enumerate(rows):
                    out.append({**r, "id": f"uuid-{r['etsy_listing_id']}"})
                res.execute.return_value.data = out
                return res
            t.upsert.side_effect = upsert_listings
        elif name == "magaza_listing_anliklari":
            # Dünkü snapshotlar:
            # 101: dün stok 20, fav 10 -> bugün stok 17, fav 13 => satis=3, fav=+3
            # 102: dün stok 5, fav 20  -> bugün stok 25 (restock!), fav 21 => satis=0, fav=+1
            # 103: ilk gün (snapshot yok) => satis=0, fav=0
            t.select.return_value.in_.return_value.lt.return_value.order.return_value.execute.return_value.data = [
                {"listing_id": "uuid-101", "tarih": "2026-11-27", "stok_miktari": 20, "favori_sayisi": 10},
                {"listing_id": "uuid-102", "tarih": "2026-11-27", "stok_miktari": 5, "favori_sayisi": 20},
            ]
            def upsert_anliklar(rows, **kw):
                captured["anliklar"] = rows
                res = MagicMock()
                res.execute.return_value.data = rows
                return res
            t.upsert.side_effect = upsert_anliklar
        elif name == "magaza_anliklari":
            t.upsert.return_value.execute.return_value.data = []
        return t

    sb.table.side_effect = table_side_effect

    etsy_listings = {
        "results": [
            {"listing_id": 101, "title": "Satilan Urun", "price": {"amount": 1000, "divisor": 100, "currency_code": "USD"}, "tags": [], "num_favorers": 13, "views": 100, "quantity": 17},
            {"listing_id": 102, "title": "Restock Urun", "price": {"amount": 1200, "divisor": 100, "currency_code": "USD"}, "tags": [], "num_favorers": 21, "views": 80, "quantity": 25},
            {"listing_id": 103, "title": "Ilk Gun Urun", "price": {"amount": 800, "divisor": 100, "currency_code": "USD"}, "tags": [], "num_favorers": 5, "views": 20, "quantity": 10},
        ]
    }

    async def fake_etsy_get(url, params=None, **kwargs):
        if "/listings/active" in url:
            return etsy_listings
        return {"shop_id": 555, "transaction_sold_count": 100, "review_count": 10, "review_average": 4.9}

    with patch("routers.magazalar._etsy_get", side_effect=fake_etsy_get):
        await magaza_urunlerini_senkronize_et(sb=sb, magaza_id="m1", shop_id=555)

    assert "anliklar" in captured
    by_lid = {r["listing_id"]: r for r in captured["anliklar"]}
    assert by_lid["uuid-101"]["gunluk_satis"] == 3
    assert by_lid["uuid-101"]["gunluk_favori_degisim"] == 3
    assert by_lid["uuid-102"]["gunluk_satis"] == 0  # Restock eksi yazmamalı
    assert by_lid["uuid-102"]["gunluk_favori_degisim"] == 1
    assert by_lid["uuid-103"]["gunluk_satis"] == 0


def test_magaza_listinglari_gunluk_gecmis_ile_doner():
    """GET /api/magazalar/{id}/listinglar günlük satış ve 7 günlük geçmişi döndürmeli."""
    sb = _mock_sb()

    def table_side_effect(name):
        t = MagicMock()
        if name == "magaza_listingleri":
            t.select.return_value.eq.return_value.order.return_value.execute.return_value.data = [
                {"id": "l1", "magaza_id": "m1", "etsy_listing_id": 101, "baslik": "Urun 1", "fiyat": 15.0, "favori_sayisi": 40, "takip_aktif": True},
                {"id": "l2", "magaza_id": "m1", "etsy_listing_id": 102, "baslik": "Ilk Gun Urun", "fiyat": 9.0, "favori_sayisi": 5, "takip_aktif": True},
            ]
        elif name == "magaza_listing_anliklari":
            t.select.return_value.in_.return_value.order.return_value.limit.return_value.execute.return_value.data = [
                {"listing_id": "l1", "tarih": "2026-11-28", "gunluk_satis": 4, "gunluk_favori_degisim": 2, "stok_miktari": 12},
                {"listing_id": "l1", "tarih": "2026-11-27", "gunluk_satis": 1, "gunluk_favori_degisim": 1, "stok_miktari": 16},
                {"listing_id": "l2", "tarih": "2026-11-28", "gunluk_satis": 0, "gunluk_favori_degisim": 0, "stok_miktari": 10},
            ]
        return t

    sb.table.side_effect = table_side_effect
    app.dependency_overrides[supabase_al] = lambda: sb
    try:
        res = client.get("/api/magazalar/m1/listinglar")
        assert res.status_code == 200
        data = res.json()
        assert data[0]["bugun_satis"] == 4
        assert data[0]["toplam_takip_satis"] == 5
        assert data[0]["ilk_gun_mu"] is False
        assert len(data[0]["gunluk_gecmis"]) == 2
        assert data[1]["bugun_satis"] is None
        assert data[1]["ilk_gun_mu"] is True
    finally:
        app.dependency_overrides.clear()
