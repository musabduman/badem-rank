-- ============================================================
-- BADEM RANK — Mağaza Takibi Tabloları Migration
-- Supabase SQL Editor'da çalıştır
-- ============================================================

-- UUID eklentisi (zaten varsa atlar)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- 1. MAGAZALAR — Takip edilen Etsy mağazaları
-- ============================================================
CREATE TABLE IF NOT EXISTS magazalar (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    shop_id         BIGINT NOT NULL UNIQUE,
    shop_name       TEXT NOT NULL,
    arama_alani     TEXT,              -- hangi niche/keyword'den bulundu
    takip_aktif     BOOLEAN DEFAULT TRUE,
    olusturuldu     TIMESTAMPTZ DEFAULT NOW(),
    guncellendi     TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE magazalar IS 'Takip edilen Etsy mağazaları';

-- ============================================================
-- 2. MAGAZA_ANLIKLARI — Günlük mağaza istatistikleri
-- ============================================================
CREATE TABLE IF NOT EXISTS magaza_anliklari (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    magaza_id               UUID NOT NULL REFERENCES magazalar(id) ON DELETE CASCADE,
    tarih                   DATE DEFAULT CURRENT_DATE,
    toplam_satis            INTEGER,
    yorum_sayisi            INTEGER,
    yorum_puani             NUMERIC(3,2),
    aktif_listing_sayisi    INTEGER,
    UNIQUE(magaza_id, tarih)
);

COMMENT ON TABLE magaza_anliklari IS 'Mağaza bazlı günlük snapshot';

-- ============================================================
-- 3. MAGAZA_LISTINGLERI — Takip edilen mağazaların ürünleri
-- ============================================================
CREATE TABLE IF NOT EXISTS magaza_listingleri (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    magaza_id           UUID NOT NULL REFERENCES magazalar(id) ON DELETE CASCADE,
    etsy_listing_id     BIGINT NOT NULL,
    baslik              TEXT,
    fiyat               NUMERIC(10,2),
    para_birimi         TEXT DEFAULT 'USD',
    listing_type        TEXT,
    etiketler           TEXT[],
    favori_sayisi       INTEGER DEFAULT 0,
    goruntuleme         INTEGER DEFAULT 0,
    stok_miktari        INTEGER DEFAULT 0,
    listing_url         TEXT,
    takip_aktif         BOOLEAN DEFAULT TRUE,
    ilk_goruldu         DATE DEFAULT CURRENT_DATE,
    son_guncellendi     DATE DEFAULT CURRENT_DATE,
    UNIQUE(magaza_id, etsy_listing_id)
);

COMMENT ON TABLE magaza_listingleri IS 'Takip edilen mağazaların ürün listelemeleri';

-- ============================================================
-- 4. MAGAZA_LISTING_ANLIKLARI — Ürün bazlı günlük satış snapshot'ları
-- ============================================================
CREATE TABLE IF NOT EXISTS magaza_listing_anliklari (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    listing_id              UUID NOT NULL REFERENCES magaza_listingleri(id) ON DELETE CASCADE,
    tarih                   DATE NOT NULL DEFAULT CURRENT_DATE,
    stok_miktari            INTEGER DEFAULT 0,
    favori_sayisi           INTEGER DEFAULT 0,
    goruntuleme             INTEGER DEFAULT 0,
    fiyat                   NUMERIC(10,2),
    gunluk_satis            INTEGER DEFAULT 0,
    gunluk_favori_degisim   INTEGER DEFAULT 0,
    UNIQUE(listing_id, tarih)
);

COMMENT ON TABLE magaza_listing_anliklari IS 'Takip edilen mağaza ürünlerinin günlük stok/favori snapshot ve satış deltası';

-- ============================================================
-- İNDEKSLER
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_magaza_takip ON magazalar(takip_aktif);
CREATE INDEX IF NOT EXISTS idx_magaza_anlik_tarih ON magaza_anliklari(magaza_id, tarih DESC);
CREATE INDEX IF NOT EXISTS idx_magaza_listing_magaza ON magaza_listingleri(magaza_id);
CREATE INDEX IF NOT EXISTS idx_magaza_listing_takip ON magaza_listingleri(takip_aktif);
CREATE INDEX IF NOT EXISTS idx_magaza_listing_anlik_tarih ON magaza_listing_anliklari(listing_id, tarih DESC);

-- ============================================================
-- Trigger: guncellendi otomatik güncelleme
-- ============================================================
DROP TRIGGER IF EXISTS magazalar_guncellendi_trigger ON magazalar;
CREATE TRIGGER magazalar_guncellendi_trigger
    BEFORE UPDATE ON magazalar
    FOR EACH ROW EXECUTE FUNCTION guncelleme_zamani_ayarla();
