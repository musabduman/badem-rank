-- ============================================================
-- BADEM RANK — Supabase Veritabanı Şeması
-- Supabase SQL Editor'da çalıştır
-- ============================================================

-- UUID eklentisi (Supabase'de genellikle aktif gelir)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- 1. KEYWORDS — Takip edilen arama kelimeleri
-- ============================================================
CREATE TABLE IF NOT EXISTS keywords (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    keyword         TEXT NOT NULL UNIQUE,
    kategori        TEXT,                          -- ör: "el örgüsü", "dijital ürün"
    aciklama        TEXT,
    aktif           BOOLEAN DEFAULT TRUE,          -- false ise scrape edilmez
    olusturuldu     TIMESTAMPTZ DEFAULT NOW(),
    guncellendi     TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE keywords IS 'Takip edilen Etsy arama kelimeleri';

-- ============================================================
-- 2. KEYWORD_ANLIKLARI — Günlük keyword istatistikleri
-- ============================================================
CREATE TABLE IF NOT EXISTS keyword_anliklari (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    keyword_id              UUID NOT NULL REFERENCES keywords(id) ON DELETE CASCADE,
    cekilme_tarihi          DATE NOT NULL DEFAULT CURRENT_DATE,
    listing_sayisi          INTEGER,               -- bu keyword'de toplam kaç listing var
    ort_fiyat               DECIMAL(10, 2),        -- ortalama fiyat (USD)
    min_fiyat               DECIMAL(10, 2),
    max_fiyat               DECIMAL(10, 2),
    star_seller_sayisi      INTEGER,               -- ilk sayfada star seller sayısı
    ilk_sayfa_listing_sayisi INTEGER,              -- birinci sayfada kaç listing çektik
    rekabet_skoru           INTEGER,               -- 1-100 arası hesaplanan skor
    UNIQUE (keyword_id, cekilme_tarihi)
);

COMMENT ON TABLE keyword_anliklari IS 'Her gün için keyword bazlı istatistik snapshot''ı';

-- ============================================================
-- 3. LISTINGLAR — Etsy ürün listelemeleri
-- ============================================================
CREATE TABLE IF NOT EXISTS listinglar (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    etsy_listing_id     BIGINT NOT NULL UNIQUE,
    keyword_id          UUID REFERENCES keywords(id) ON DELETE SET NULL,
    magaza_adi          TEXT NOT NULL,
    baslik              TEXT NOT NULL,
    fiyat               DECIMAL(10, 2),
    para_birimi         TEXT DEFAULT 'USD',
    etiketler           TEXT[],                   -- Etsy tag'leri (array)
    resim_url           TEXT,
    favori_sayisi       INTEGER DEFAULT 0,
    yorum_sayisi        INTEGER DEFAULT 0,
    satis_tahmini       INTEGER DEFAULT 0,        -- scrape'den gelen tahmini satış
    star_seller_mi      BOOLEAN DEFAULT FALSE,
    magaza_yasi_gun     INTEGER,                  -- mağaza kaç gündür açık
    listing_url         TEXT,
    ilk_goruldu         DATE DEFAULT CURRENT_DATE,
    son_guncellendi     DATE DEFAULT CURRENT_DATE
);

COMMENT ON TABLE listinglar IS 'Etsy''den çekilen ürün listelemeleri';

-- ============================================================
-- 4. LISTING_GUNLUK_ANLIKLARI — Günlük delta hesabı için
-- ============================================================
CREATE TABLE IF NOT EXISTS listing_gunluk_anliklari (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    listing_id              UUID NOT NULL REFERENCES listinglar(id) ON DELETE CASCADE,
    tarih                   DATE NOT NULL DEFAULT CURRENT_DATE,
    favori_sayisi           INTEGER DEFAULT 0,
    yorum_sayisi            INTEGER DEFAULT 0,
    satis_tahmini           INTEGER DEFAULT 0,
    -- Günlük değişim (önceki günle fark — backend tarafından hesaplanır)
    gunluk_favori_degisim   INTEGER DEFAULT 0,
    gunluk_yorum_degisim    INTEGER DEFAULT 0,
    gunluk_satis_degisim    INTEGER DEFAULT 0,    -- ana satış göstergesi
    UNIQUE (listing_id, tarih)
);

COMMENT ON TABLE listing_gunluk_anliklari IS 'Listing bazlı günlük snapshot ve delta değerleri';

-- ============================================================
-- 5. PAZAR_RAPORLARI — LLM tarafından üretilen raporlar
-- ============================================================
CREATE TABLE IF NOT EXISTS pazar_raporlari (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    keyword_id      UUID REFERENCES keywords(id) ON DELETE CASCADE,
    rapor_tarihi    DATE NOT NULL DEFAULT CURRENT_DATE,
    rapor_tipi      TEXT NOT NULL,                -- 'gunluk_ozet' | 'etiket_analizi' | 'fiyat_analizi'
    icerik          TEXT NOT NULL,                -- LLM çıktısı (markdown)
    kullanilan_model TEXT,                        -- ör: 'llama3.1:8b'
    olusturuldu     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (keyword_id, rapor_tarihi, rapor_tipi)
);

COMMENT ON TABLE pazar_raporlari IS 'LLM tarafından üretilen pazar analiz raporları (cache)';

-- ============================================================
-- 6. SCRAPE_LOGLARI — Her scrape işleminin kaydı
-- ============================================================
CREATE TABLE IF NOT EXISTS scrape_loglari (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    keyword             TEXT,
    durum               TEXT NOT NULL,             -- 'basarili' | 'hata' | 'kismен_başarılı'
    cekilen_listing     INTEGER DEFAULT 0,
    hata_mesaji         TEXT,
    baslama_zamani      TIMESTAMPTZ DEFAULT NOW(),
    bitis_zamani        TIMESTAMPTZ,
    sure_saniye         DECIMAL(8, 2)
);

COMMENT ON TABLE scrape_loglari IS 'Scraping işlemlerinin log kayıtları';

-- ============================================================
-- İNDEKSLER — Sorgu performansı için
-- ============================================================

-- keyword_anliklari: keyword + tarih bazlı sorgular
CREATE INDEX IF NOT EXISTS idx_kw_anlik_keyword_tarih 
    ON keyword_anliklari(keyword_id, cekilme_tarihi DESC);

-- listinglar: keyword bazlı filtreleme
CREATE INDEX IF NOT EXISTS idx_listing_keyword 
    ON listinglar(keyword_id);

-- listinglar: etsy_listing_id ile hızlı upsert
CREATE INDEX IF NOT EXISTS idx_listing_etsy_id 
    ON listinglar(etsy_listing_id);

-- listing_gunluk_anliklari: listing + tarih bazlı sorgular
CREATE INDEX IF NOT EXISTS idx_gunluk_listing_tarih 
    ON listing_gunluk_anliklari(listing_id, tarih DESC);

-- listing_gunluk_anliklari: tarih bazlı toplu sorgular
CREATE INDEX IF NOT EXISTS idx_gunluk_tarih 
    ON listing_gunluk_anliklari(tarih DESC);

-- ============================================================
-- YARDIMCI FONKSİYON — guncellendi otomatik güncelleme
-- ============================================================
CREATE OR REPLACE FUNCTION guncelleme_zamani_ayarla()
RETURNS TRIGGER AS $$
BEGIN
    NEW.guncellendi = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER keywords_guncellendi_trigger
    BEFORE UPDATE ON keywords
    FOR EACH ROW EXECUTE FUNCTION guncelleme_zamani_ayarla();

-- ============================================================
-- ÖRNEK VERİ — Test için (isteğe bağlı, silebilirsin)
-- ============================================================
-- INSERT INTO keywords (keyword, kategori, aciklama) VALUES
--     ('crochet hat', 'el örgüsü', 'Örme şapka araması'),
--     ('digital planner', 'dijital ürün', 'Dijital planlayıcı araması'),
--     ('handmade bracelet', 'takı', 'El yapımı bileklik araması');
