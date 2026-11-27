-- ============================================================
-- BADEM RANK — Ürün Bazlı Günlük Satış Snapshot Tablosu
-- Supabase SQL Editor'da çalıştır (magazalar_migration.sql sonrası)
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

CREATE INDEX IF NOT EXISTS idx_magaza_listing_anlik_tarih
    ON magaza_listing_anliklari(listing_id, tarih DESC);
