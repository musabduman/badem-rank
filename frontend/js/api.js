// Backend URL'sini otomatik ayarlar: Lokaldeysek 8000 portu, sunucudaysak Render URL'si
const IS_LOCAL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
const API_BASE = IS_LOCAL 
    ? "http://localhost:8000/api" 
    : "https://SENIN_RENDER_URLN.onrender.com/api"; // TODO: Render'a deploy edince burayı kendi URL'inle değiştir!

const api = {
    // Yeni kelime ara ve kazı (veya varsa döndür)
    async searchKeyword(keyword) {
        try {
            const res = await fetch(`${API_BASE}/keywords`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ keyword: keyword })
            });
            
            // Eğer daha önceden eklendiyse (409 Conflict) liste endpoint'inden o kelimenin ID'sini bulmalıyız
            // Şimdilik hata yönetimi ve akışı basitleştirmek için listeyi çekeceğiz
            if (res.status === 409) {
                return this.findKeywordId(keyword);
            }
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

    async getTagAnalytics(keywordId) {
        const res = await fetch(`${API_BASE}/analitik/etiketler?keyword_id=${keywordId}`);
        return await res.json();
    },

    async getPriceAnalytics(keywordId) {
        const res = await fetch(`${API_BASE}/analitik/fiyat?keyword_id=${keywordId}`);
        return await res.json();
    }
};
