// DOM Elements
const searchInput = document.getElementById("searchInput");
const searchBtn = document.getElementById("searchBtn");
const currentKeywordTitle = document.getElementById("currentKeywordTitle");
const dataStatus = document.getElementById("dataStatus");

// Charts
let priceChartInstance = null;
let tagsChartInstance = null;

let currentKeywordId = null;

// AI Panel Toggle
const aiPanelToggle = document.getElementById("aiPanelToggle");
const aiPanelClose = document.getElementById("aiPanelClose");
const aiPanel = document.getElementById("aiPanel");
const aiChatArea = document.getElementById("aiChatArea");

aiPanelToggle.addEventListener("click", () => aiPanel.classList.remove("closed"));
aiPanelClose.addEventListener("click", () => aiPanel.classList.add("closed"));

// Arama
searchBtn.addEventListener("click", async () => {
    const text = searchInput.value.trim();
    if (!text) return;
    
    currentKeywordTitle.textContent = text;
    dataStatus.textContent = "Analiz Ediliyor...";
    dataStatus.className = "badge";
    
    const kw = await api.searchKeyword(text);
    if (!kw) {
        dataStatus.textContent = "Hata oluştu";
        dataStatus.classList.add("error");
        return;
    }
    
    currentKeywordId = kw.id;
    await loadDashboard(currentKeywordId);
});

searchInput.addEventListener("keypress", (e) => {
    if (e.key === "Enter") searchBtn.click();
});

// Veri Yükleme
async function loadDashboard(keywordId) {
    try {
        const details = await api.getKeywordDetails(keywordId);
        const anlik = details.son_anlik;

        if (anlik) {
            document.getElementById("statListingCount").textContent = anlik.listing_sayisi || "-";
            document.getElementById("statCompetition").textContent = anlik.rekabet_skoru || "-";
            document.getElementById("statAvgPrice").textContent = anlik.ort_fiyat ? "$" + anlik.ort_fiyat : "-";
            const ratio = anlik.ilk_sayfa_listing_sayisi ? Math.round((anlik.star_seller_sayisi / anlik.ilk_sayfa_listing_sayisi) * 100) : 0;
            document.getElementById("statStarSeller").textContent = "%" + ratio;
            
            dataStatus.textContent = "Analiz Tamamlandı";
            dataStatus.className = "badge success";
        } else {
            dataStatus.textContent = "Arka planda veri çekiliyor...";
        }

        // Listing Tablosu
        await updateListingsTable(keywordId, "satis_tahmini");

        // Grafikler
        const tagData = await api.getTagAnalytics(keywordId);
        const priceData = await api.getPriceAnalytics(keywordId);
        
        renderTagsChart(tagData.etiketler || []);
        renderPriceChart(priceData);

    } catch (e) {
        console.error("Dashboard yüklenirken hata:", e);
    }
}

async function updateListingsTable(keywordId, sortField) {
    const listings = await api.getListings(keywordId, sortField, "desc");
    const tbody = document.getElementById("listingsTableBody");
    tbody.innerHTML = "";

    if (listings.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">Henüz veri yok. Arka plan işleminin bitmesini bekleyin.</td></tr>`;
        return;
    }

    listings.slice(0, 50).forEach(l => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td><img src="${l.resim_url || 'https://via.placeholder.com/48'}" class="listing-img" alt="Ürün Resmi"></td>
            <td>
                <div style="font-weight: 500; font-size: 0.9rem; margin-bottom: 0.2rem; max-width: 300px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                    <a href="${l.listing_url}" target="_blank" style="color: var(--text-main); text-decoration: none;">${l.baslik}</a>
                </div>
                <div style="font-size: 0.8rem; color: var(--text-muted);">${l.magaza_adi}</div>
            </td>
            <td style="font-weight: 500;">$${l.fiyat || '-'}</td>
            <td>${l.favori_sayisi}</td>
            <td style="color: var(--primary); font-weight: 600;">${l.satis_tahmini}</td>
            <td>${l.star_seller_mi ? '<span class="badge" style="background: hsl(40, 90%, 95%); color: hsl(40, 90%, 40%); border: none;">Star Seller</span>' : '-'}</td>
        `;
        tbody.appendChild(tr);
    });
}

document.getElementById("sortSelect").addEventListener("change", (e) => {
    if (currentKeywordId) {
        updateListingsTable(currentKeywordId, e.target.value);
    }
});

// Chart.js Renders
function renderTagsChart(etiketler) {
    const ctx = document.getElementById("tagsChart").getContext("2d");
    if (tagsChartInstance) tagsChartInstance.destroy();

    const top10 = etiketler.slice(0, 10);
    
    tagsChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: top10.map(t => t.etiket.substring(0, 15)),
            datasets: [{
                label: 'Ortalama Satış Tahmini',
                data: top10.map(t => t.ort_satis_tahmini),
                backgroundColor: 'hsl(152, 60%, 40%)',
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: { y: { beginAtZero: true } }
        }
    });
}

function renderPriceChart(priceData) {
    const ctx = document.getElementById("priceChart").getContext("2d");
    if (priceChartInstance) priceChartInstance.destroy();

    const data = [
        priceData.segment_0_25 || 0,
        priceData.segment_25_50 || 0,
        priceData.segment_50_100 || 0,
        priceData.segment_100_plus || 0
    ];

    priceChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['$0 - $25', '$25 - $50', '$50 - $100', '$100+'],
            datasets: [{
                data: data,
                backgroundColor: [
                    'hsl(152, 60%, 40%)',
                    'hsl(152, 50%, 55%)',
                    'hsl(152, 40%, 70%)',
                    'hsl(152, 30%, 85%)'
                ],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '70%',
            plugins: {
                legend: { position: 'right' }
            }
        }
    });
}

// Basit AI Chat Simülasyonu / Entegrasyonu (Şimdilik statik - SSE stream backend'den bağlanabilir)
const btnQuickReport = document.getElementById("btnQuickReport");
btnQuickReport.addEventListener("click", async () => {
    if (!currentKeywordId) return;
    
    // Yükleniyor mesajı
    const waitMsg = document.createElement("div");
    waitMsg.className = "message assistant";
    waitMsg.textContent = "Veriler analiz ediliyor...";
    aiChatArea.appendChild(waitMsg);
    aiChatArea.scrollTop = aiChatArea.scrollHeight;

    try {
        const res = await fetch(`${API_BASE}/llm/rapor-olustur`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ keyword_id: currentKeywordId, rapor_tipi: "gunluk_ozet", yeniden_olustur: false })
        });
        const data = await res.json();
        
        waitMsg.textContent = data.icerik || "Rapor alınamadı.";
    } catch (e) {
        waitMsg.textContent = "Bağlantı hatası.";
    }
});
