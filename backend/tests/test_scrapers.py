import pytest
from bs4 import BeautifulSoup
from scrapers.etsy_arama import _fiyat_coz, _listing_parse_et

def test_fiyat_coz():
    assert _fiyat_coz("$29.99") == 29.99
    assert _fiyat_coz("€15,00") == 15.00
    assert _fiyat_coz("29.99 USD") == 29.99
    assert _fiyat_coz("1.299,99") == 1299.99
    assert _fiyat_coz("1299.99") == 1299.99
    assert _fiyat_coz("Bilinmiyor") is None
    assert _fiyat_coz(None) is None

def test_listing_parse_et():
    html = """
    <div class="js-merch-stash-check-listing">
        <a href="https://www.etsy.com/listing/123456789/test-item?click_key=xxx">
            <h3>Test Baslik</h3>
            <p class="shop-name">Test Magaza</p>
            <p class="currency-value" data-currency-value="45.50">45.50</p>
            <span class="star-seller-badge">Star Seller</span>
        </a>
    </div>
    """
    kart = BeautifulSoup(html, "lxml").div
    sonuc = _listing_parse_et(kart)
    
    assert sonuc is not None
    assert sonuc["etsy_listing_id"] == 123456789
    assert sonuc["baslik"] == "Test Baslik"
    assert sonuc["fiyat"] == 45.50
    assert sonuc["magaza_adi"] == "Test Magaza"
    assert sonuc["star_seller_mi"] is True
    assert sonuc["listing_url"] == "https://www.etsy.com/listing/123456789/test-item"

def test_listing_parse_et_eksik_veri():
    html = """
    <div class="js-merch-stash-check-listing">
        <a href="https://www.etsy.com/listing/987654321/another-item">
            <!-- Eksik bilgiler -->
        </a>
    </div>
    """
    kart = BeautifulSoup(html, "lxml").div
    sonuc = _listing_parse_et(kart)
    
    assert sonuc is not None
    assert sonuc["etsy_listing_id"] == 987654321
    assert sonuc["baslik"] == "Bilinmiyor"
    assert sonuc["fiyat"] is None
    assert sonuc["magaza_adi"] == "Bilinmiyor"
    assert sonuc["star_seller_mi"] is False
