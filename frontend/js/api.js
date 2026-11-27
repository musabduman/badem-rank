// Backend URL — lokal vs Render
const IS_LOCAL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
const API_BASE = IS_LOCAL
    ? "http://localhost:8000/api"
    : "https://badem-rank.onrender.com/api";

const api = {

    // ─── Keyword Aracı ───────────────────────────────────────

    async searchKeyword(keyword) {
        try {
            const res = await fetch(`${API_BASE}/keywords`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ keyword })
            });
            if (res.status === 409) return this.findKeywordId(keyword);
            if (!res.ok) throw new Error("API Hatası: " + res.status);
            return await res.json();
        } catch (e) {
            console.error(e);
            return null;
        }
    },

    async findKeywordId(keywordText) {
        try {
            const res = await fetch(`${API_BASE}/keywords`);
            const data = await res.json();
            const found = data.find(item => item.keyword.keyword === keywordText.toLowerCase());
            return found ? found.keyword : null;
        } catch (e) {
            return null;
        }
    },

    async getKeywordDetails(keywordId) {
        const res = await fetch(`${API_BASE}/keywords/${keywordId}`);
        return await res.json();
    },

    async getListings(keywordId, sort = "satis_tahmini", order = "desc") {
        const res = await fetch(`${API_BASE}/listinglar?keyword_id=${keywordId}&siralama=${sort}&siralama_yonu=${order}`);
        return await res.json();
    },

    // ─── Mağaza Takibi ────────────────────────────────────────

    async magazaAra(keyword, tur = "alan") {
        const res = await fetch(`${API_BASE}/magazalar/ara?keyword=${encodeURIComponent(keyword)}&tur=${tur}`, {
            method: "POST"
        });
        if (!res.ok) throw new Error("Arama hatası: " + res.status);
        return await res.json();
    },

    async etsyMagazaListingleri(shopId) {
        const res = await fetch(`${API_BASE}/magazalar/etsy/${shopId}/listinglar`);
        if (!res.ok) throw new Error("Ürün önizleme hatası: " + res.status);
        return await res.json();
    },

    async magazaEkle(shopId, shopName, aramaAlani, haricEtsyIds = []) {
        const res = await fetch(`${API_BASE}/magazalar/ekle`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                shop_id: shopId,
                shop_name: shopName,
                arama_alani: aramaAlani,
                haric_etsy_ids: haricEtsyIds
            })
        });
        if (!res.ok) throw new Error("Ekleme hatası: " + res.status);
        return await res.json();
    },

    async magazaTakipBirak(magazaId) {
        const res = await fetch(`${API_BASE}/magazalar/${magazaId}`, { method: "DELETE" });
        if (!res.ok) throw new Error("Silme hatası: " + res.status);
        return await res.json();
    },

    async takipMagazalar() {
        const res = await fetch(`${API_BASE}/magazalar`);
        if (!res.ok) throw new Error("Liste hatası: " + res.status);
        return await res.json();
    },

    async magazaListingleri(magazaId) {
        const res = await fetch(`${API_BASE}/magazalar/${magazaId}/listinglar`);
        if (!res.ok) throw new Error("Listing hatası: " + res.status);
        return await res.json();
    },

    async listingTakipGuncelle(listingId, takipAktif) {
        const res = await fetch(`${API_BASE}/magaza-listingleri/${listingId}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ takip_aktif: takipAktif })
        });
        if (!res.ok) throw new Error("Güncelleme hatası: " + res.status);
        return await res.json();
    }
};
