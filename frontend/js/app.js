// ─── Sayfa Yönetimi ───────────────────────────────────────────────────────

const navItems = document.querySelectorAll('.nav-item');
const pages = document.querySelectorAll('.page-content');

function sayfaGoster(pageId) {
    pages.forEach(p => p.classList.add('hidden'));
    navItems.forEach(n => n.classList.remove('active'));

    const target = document.getElementById('page-' + pageId);
    if (target) target.classList.remove('hidden');

    const navItem = document.querySelector(`[data-page="${pageId}"]`);
    if (navItem) navItem.classList.add('active');

    if (pageId === 'dashboard') loadDashboard();
}

navItems.forEach(item => {
    item.addEventListener('click', (e) => {
        e.preventDefault();
        sayfaGoster(item.dataset.page);
    });
});

// ─── KEYWORD ARACI ────────────────────────────────────────────────────────

let currentKeywordId = null;

const searchBtn = document.getElementById('searchBtn');
const searchInput = document.getElementById('searchInput');

searchBtn.addEventListener('click', async () => {
    const text = searchInput.value.trim();
    if (!text) return;

    setStatus('dataStatus', 'Veri Çekiliyor...', 'warning');
    searchBtn.disabled = true;
    searchBtn.textContent = '⏳ Bekleniyor...';
    document.getElementById('currentKeywordTitle').textContent = text;

    try {
        const kw = await api.searchKeyword(text);
        if (!kw) { setStatus('dataStatus', 'Hata oluştu', 'error'); return; }
        currentKeywordId = kw.id;

        await keywordDashboard(currentKeywordId);

        for (let i = 0; i < 12; i++) {
            await bekle(2500);
            const details = await api.getKeywordDetails(currentKeywordId);
            if (details?.son_anlik) {
                await keywordDashboard(currentKeywordId);
                break;
            }
        }
    } catch (e) {
        console.error(e);
        setStatus('dataStatus', 'Hata oluştu', 'error');
    } finally {
        searchBtn.disabled = false;
        searchBtn.textContent = 'Analiz Et';
    }
});

searchInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') searchBtn.click(); });

async function keywordDashboard(kwId) {
    try {
        const sortField = document.getElementById('sortSelect').value || 'satis_tahmini';
        const [details, listings] = await Promise.all([
            api.getKeywordDetails(kwId),
            api.getListings(kwId, sortField, 'desc')
        ]);

        const anlik = details.son_anlik;
        if (anlik) {
            document.getElementById('statListingCount').textContent = anlik.listing_sayisi ?? '-';
            document.getElementById('statCompetition').textContent = anlik.rekabet_skoru ?? '-';
            document.getElementById('statAvgPrice').textContent = anlik.ort_fiyat ? '$' + anlik.ort_fiyat : '-';
            const ratio = anlik.ilk_sayfa_listing_sayisi
                ? Math.round((anlik.star_seller_sayisi / anlik.ilk_sayfa_listing_sayisi) * 100)
                : 0;
            document.getElementById('statStarSeller').textContent = '%' + ratio;
            setStatus('dataStatus', 'Analiz Tamamlandı', 'success');
        } else {
            setStatus('dataStatus', 'Veri çekiliyor...', 'warning');
        }

        renderListingsTableRows(listings);
    } catch (e) {
        console.error('Keyword dashboard hatası:', e);
    }
}

async function listingTabloGuncelle(kwId, sortField) {
    const tbody = document.getElementById('listingsTableBody');
    tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted" style="padding:1.5rem">Yükleniyor...</td></tr>';

    try {
        const listings = await api.getListings(kwId, sortField, 'desc');
        renderListingsTableRows(listings);
    } catch (e) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">Yükleme hatası.</td></tr>';
    }
}

function renderListingsTableRows(listings) {
    const tbody = document.getElementById('listingsTableBody');
    if (!listings || !listings.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted" style="padding:1.5rem">Henüz veri yok. Arka plan işleminin bitmesini bekleyin.</td></tr>';
        return;
    }

    tbody.innerHTML = listings.slice(0, 50).map(l => {
        const etiketler = (l.etiketler || []).slice(0, 5)
            .map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('');
        return `
            <tr>
                <td>
                    <div class="listing-title">
                        <a href="${escapeAttr(l.listing_url)}" target="_blank">${escapeHtml(l.baslik)}</a>
                    </div>
                    <div class="listing-shop">${escapeHtml(l.magaza_adi)}</div>
                </td>
                <td><strong>$${l.fiyat ?? '-'}</strong></td>
                <td>${l.favori_sayisi ?? '-'}</td>
                <td class="highlight">${l.satis_tahmini ?? '-'}</td>
                <td>${etiketler || '-'}</td>
                <td>${l.star_seller_mi ? '<span class="badge badge-star">⭐ Star</span>' : '-'}</td>
            </tr>
        `;
    }).join('');
}

document.getElementById('sortSelect').addEventListener('change', (e) => {
    if (currentKeywordId) listingTabloGuncelle(currentKeywordId, e.target.value);
});

// ─── MAĞAZA TAKİBİ ────────────────────────────────────────────────────────

const magazaSearchBtn = document.getElementById('magazaSearchBtn');
const magazaSearchInput = document.getElementById('magazaSearchInput');
const aramaType = document.getElementById('aramaType');

magazaSearchBtn.addEventListener('click', magazaAra);
magazaSearchInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') magazaAra(); });

async function magazaAra() {
    const text = magazaSearchInput.value.trim();
    if (!text) return;

    const tur = aramaType.value;
    const statusEl = document.getElementById('magazaSearchStatus');
    const resultsEl = document.getElementById('magazaSearchResults');

    statusEl.textContent = `${tur === 'alan' ? 'Alan' : 'Mağaza'} aranıyor: "${text}"...`;
    statusEl.className = 'search-status loading';
    statusEl.classList.remove('hidden');
    resultsEl.classList.add('hidden');
    magazaSearchBtn.disabled = true;
    magazaSearchBtn.textContent = '⏳ Aranıyor...';

    try {
        const sonuclar = await api.magazaAra(text, tur);

        if (!sonuclar.length) {
            statusEl.textContent = 'Sonuç bulunamadı.';
            statusEl.className = 'search-status';
            return;
        }

        statusEl.textContent = `${sonuclar.length} mağaza bulundu.`;
        statusEl.className = 'search-status';
        renderMagazaSonuclar(sonuclar, tur === 'alan' ? text : null);
        resultsEl.classList.remove('hidden');

    } catch (e) {
        statusEl.textContent = 'Arama sırasında hata: ' + e.message;
        statusEl.className = 'search-status error';
    } finally {
        magazaSearchBtn.disabled = false;
        magazaSearchBtn.textContent = 'Ara';
    }
}

function renderMagazaSonuclar(sonuclar, aramaAlani) {
    const inner = document.getElementById('magazaResultsContainer');
    inner.innerHTML = '';

    sonuclar.forEach(magaza => {
        const card = document.createElement('div');
        card.className = 'magaza-card';
        card.dataset.shopId = magaza.shop_id;
        card.dataset.shopName = magaza.shop_name;
        card.dataset.magazaId = magaza.magaza_id || '';
        card.dataset.aramaAlani = aramaAlani || '';

        card.innerHTML = `
            <div class="magaza-card-header">
                <div class="checkbox-label">
                    <input type="checkbox" class="magaza-checkbox" ${magaza.takip_ediliyor ? 'checked' : ''}>
                    <button type="button" class="magaza-name-btn">${escapeHtml(magaza.shop_name)}</button>
                </div>
                <div class="magaza-meta">
                    <span>🛒 ${(magaza.toplam_satis || 0).toLocaleString()} satış</span>
                    ${magaza.yorum_puani ? `<span>⭐ ${magaza.yorum_puani}</span>` : ''}
                    ${magaza.sonuc_sayisi ? `<span>📦 ${magaza.sonuc_sayisi} ürün bu alanda</span>` : ''}
                    <a href="${escapeAttr(magaza.url)}" target="_blank" class="btn-link">Etsy'de Gör ↗</a>
                </div>
            </div>
            <div class="magaza-listings hidden" id="listings-${magaza.shop_id}">
                <div class="listings-loading">Ürünler yükleniyor...</div>
            </div>
        `;

        inner.appendChild(card);

        const cb = card.querySelector('.magaza-checkbox');
        const listingsDiv = document.getElementById(`listings-${magaza.shop_id}`);

        cb.addEventListener('change', async (e) => {
            if (e.target.checked) {
                await magazaTakipEkleVeSenkronizeEt(card, cb, listingsDiv);
            } else {
                await magazaTakipKaldir(card, cb, listingsDiv);
            }
        });

        card.querySelector('.magaza-name-btn').addEventListener('click', () => toggleSearchListings(card, listingsDiv));
    });
}

async function magazaTakipEkleVeSenkronizeEt(card, cb, listingsDiv, haricEtsyIds = []) {
    const shopId = Number(card.dataset.shopId);
    const shopName = card.dataset.shopName;
    const aramaAlani = card.dataset.aramaAlani || null;

    cb.disabled = true;

    // Eğer ürün listesi zaten açıksa kullanıcı görsün diye tüm tikleri hemen işaretle
    if (listingsDiv.dataset.loaded === '1' && haricEtsyIds.length === 0) {
        listingsDiv.querySelectorAll('.listing-checkbox').forEach(lcb => { lcb.checked = true; });
    }

    try {
        const res = await api.magazaEkle(shopId, shopName, aramaAlani, haricEtsyIds);
        card.dataset.magazaId = res.magaza_id || '';

        if (res.listinglar && res.listinglar.length) {
            renderMagazaListingleri(listingsDiv, card, res.listinglar);
            listingsDiv.dataset.loaded = '1';
        }
    } catch (e) {
        alert('Takip eklenirken hata: ' + e.message);
        cb.checked = false;
        if (listingsDiv.dataset.loaded === '1') {
            listingsDiv.querySelectorAll('.listing-checkbox').forEach(lcb => { lcb.checked = false; });
        }
    } finally {
        cb.disabled = false;
    }
}

async function magazaTakipKaldir(card, cb, listingsDiv) {
    const shopName = card.dataset.shopName;
    let magazaId = card.dataset.magazaId;

    if (!confirm(`"${shopName}" mağazasını takipten çıkmak istediğinizden emin misiniz?`)) {
        cb.checked = true;
        return;
    }

    cb.disabled = true;
    try {
        if (!magazaId) {
            const magazalar = await api.takipMagazalar();
            const found = magazalar.find(x => x.shop_id == card.dataset.shopId);
            magazaId = found?.id;
        }
        if (magazaId) {
            await api.magazaTakipBirak(magazaId);
        }
        card.dataset.magazaId = '';
        if (listingsDiv.dataset.loaded === '1') {
            listingsDiv.querySelectorAll('.listing-checkbox').forEach(lcb => {
                lcb.checked = false;
                lcb.dataset.listingId = '';
            });
        }
    } catch (e) {
        alert('Takip kaldırılırken hata: ' + e.message);
        cb.checked = true;
    } finally {
        cb.disabled = false;
    }
}

async function toggleSearchListings(card, listingsDiv) {
    const isOpen = !listingsDiv.classList.contains('hidden');
    if (isOpen) {
        listingsDiv.classList.add('hidden');
        return;
    }

    listingsDiv.classList.remove('hidden');
    if (listingsDiv.dataset.loaded === '1') return;

    listingsDiv.innerHTML = '<div class="listings-loading">Ürünler yükleniyor...</div>';
    try {
        const shopId = Number(card.dataset.shopId);
        const urunler = await api.etsyMagazaListingleri(shopId);
        renderMagazaListingleri(listingsDiv, card, urunler);
        listingsDiv.dataset.loaded = '1';
    } catch (e) {
        listingsDiv.innerHTML = `<p class="text-muted" style="padding:1rem">Yükleme hatası: ${escapeHtml(e.message)}</p>`;
    }
}

function renderMagazaListingleri(container, card, listinglar, onCountChange = null) {
    if (!listinglar || !listinglar.length) {
        container.innerHTML = '<p class="text-muted" style="padding:1rem">Ürün bulunamadı.</p>';
        return;
    }

    const html = listinglar.map(l => {
        const etiketler = (l.etiketler || []).slice(0, 6)
            .map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('');
        const favDelta = l.gunluk_favori_degisim > 0 ? ` <span class="delta-up">+${l.gunluk_favori_degisim}</span>` : '';

        let satisRozetHtml = '';
        if (l.kayitli) {
            if (l.ilk_gun_mu) {
                satisRozetHtml = `<span class="sales-badge sales-first" title="Günlük satış farkı yarın hesaplanacak">🛒 İlk gün (stok: ${l.stok_miktari ?? 0})</span>`;
            } else {
                const s = l.bugun_satis ?? 0;
                satisRozetHtml = `<span class="sales-badge ${s > 0 ? 'sales-hot' : ''}" title="Stok değişimine göre bugünkü satış">🛒 Bugün: ${s} satış</span>`;
            }
        } else {
            satisRozetHtml = `<span class="sales-badge sales-first" title="Mevcut stok">📦 Stok: ${l.stok_miktari ?? 0}</span>`;
        }

        let gecmisHtml = '';
        if (l.kayitli && Array.isArray(l.gunluk_gecmis) && l.gunluk_gecmis.length > 1) {
            const gunler = l.gunluk_gecmis.slice(0, 7).map(g => {
                const tarihKisa = formatShortDate(g.tarih);
                return `<span class="history-pill ${g.satis > 0 ? 'hot' : ''}">${escapeHtml(tarihKisa)}: ${g.satis}</span>`;
            }).join('');
            gecmisHtml = `<div class="listing-history">${gunler}</div>`;
        }

        return `
            <div class="listing-row">
                <div class="checkbox-label">
                    <input type="checkbox" class="listing-checkbox"
                        data-listing-id="${escapeAttr(l.id || '')}"
                        data-etsy-listing-id="${escapeAttr(l.etsy_listing_id)}"
                        ${l.takip_aktif ? 'checked' : ''}>
                    <div class="listing-info">
                        <a href="${escapeAttr(l.listing_url || '#')}" target="_blank" class="listing-title-sm">${escapeHtml(l.baslik || 'İsimsiz Ürün')}</a>
                        <div class="listing-tags">${etiketler}</div>
                        ${gecmisHtml}
                    </div>
                </div>
                <div class="listing-price">$${l.fiyat ?? '-'}</div>
                <div class="listing-favs" title="Favori sayısı">${'❤️'} ${l.favori_sayisi ?? 0}${favDelta}</div>
                <div class="listing-sales">${satisRozetHtml}</div>
            </div>
        `;
    }).join('');

    container.innerHTML = `<div class="listings-inner">${html}</div>`;

    container.querySelectorAll('.listing-checkbox').forEach(cb => {
        cb.addEventListener('change', async (e) => {
            const listingId = e.target.dataset.listingId;
            const clickedEtsyId = Number(e.target.dataset.etsyListingId);
            const aktif = e.target.checked;

            // Eğer mağaza henüz takipte değilse ve kullanıcı bir ürüne tik attıysa:
            // mağazayı sadece seçili ürünleri aktif olacak şekilde takibe al.
            if (!listingId) {
                if (!aktif) return;
                const shopCb = card.querySelector('.magaza-checkbox');
                if (shopCb) shopCb.checked = true;
                const haricIds = Array.from(container.querySelectorAll('.listing-checkbox'))
                    .map(x => Number(x.dataset.etsyListingId))
                    .filter(eid => eid !== clickedEtsyId);
                await magazaTakipEkleVeSenkronizeEt(card, shopCb || e.target, container, haricIds);
                return;
            }

            try {
                cb.disabled = true;
                await api.listingTakipGuncelle(listingId, aktif);
                if (onCountChange) {
                    const activeCount = container.querySelectorAll('.listing-checkbox:checked').length;
                    onCountChange(activeCount);
                }
            } catch (err) {
                alert('Güncelleme hatası: ' + err.message);
                e.target.checked = !aktif;
            } finally {
                cb.disabled = false;
            }
        });
    });
}

// ─── DASHBOARD ────────────────────────────────────────────────────────────

async function loadDashboard() {
    const statusEl = document.getElementById('dashboardStatus');
    const listEl = document.getElementById('dashboardMagazalar');
    const emptyEl = document.getElementById('dashboardEmpty');

    statusEl.textContent = 'Yükleniyor...';
    statusEl.className = 'badge';
    listEl.innerHTML = '';

    try {
        const magazalar = await api.takipMagazalar();

        if (!magazalar.length) {
            emptyEl.classList.remove('hidden');
            statusEl.textContent = 'Mağaza yok';
            return;
        }

        emptyEl.classList.add('hidden');
        statusEl.textContent = `${magazalar.length} mağaza takipte`;
        statusEl.className = 'badge badge-success';

        magazalar.forEach(m => {
            const card = document.createElement('div');
            card.className = 'magaza-card';
            card.dataset.magazaId = m.id;
            card.dataset.shopId = m.shop_id;
            card.dataset.shopName = m.shop_name;

            const satisText = m.toplam_satis != null
                ? `Toplam: ${Number(m.toplam_satis).toLocaleString()} satış${m.gunluk_satis_artis > 0 ? ` (+${m.gunluk_satis_artis} bugün)` : ''}`
                : 'Satış verisi bekleniyor';
            const puanHtml = m.yorum_puani ? `<span>⭐ ${m.yorum_puani}</span>` : '';
            const urunCount = m.takip_edilen_urun_sayisi ?? 0;

            card.innerHTML = `
                <div class="magaza-card-header">
                    <div class="magaza-card-left">
                        <button type="button" class="magaza-name-btn dash-name-btn">${escapeHtml(m.shop_name)}</button>
                        ${m.arama_alani ? `<span class="tag">${escapeHtml(m.arama_alani)}</span>` : ''}
                        <span class="badge dash-count-badge">${urunCount} ürün takip ediliyor</span>
                    </div>
                    <div class="magaza-meta">
                        <span>🛒 ${satisText}</span>
                        ${puanHtml}
                        <button type="button" class="btn-danger">Bırak ✕</button>
                    </div>
                </div>
                <div class="magaza-listings hidden" id="dash-listings-${m.id}">
                    <div class="listings-loading">Yükleniyor...</div>
                </div>
            `;

            listEl.appendChild(card);

            const listingsDiv = document.getElementById(`dash-listings-${m.id}`);
            const countBadge = card.querySelector('.dash-count-badge');

            card.querySelector('.dash-name-btn').addEventListener('click', () => {
                toggleDashListings(m.id, card, listingsDiv, (n) => {
                    countBadge.textContent = `${n} ürün takip ediliyor`;
                });
            });

            card.querySelector('.btn-danger').addEventListener('click', async () => {
                if (!confirm(`"${m.shop_name}" mağazasını takipten çıkmak istediğinizden emin misiniz?`)) return;
                try {
                    await api.magazaTakipBirak(m.id);
                    card.remove();
                    const remaining = listEl.querySelectorAll('.magaza-card').length;
                    if (!remaining) {
                        emptyEl.classList.remove('hidden');
                        statusEl.textContent = 'Mağaza yok';
                        statusEl.className = 'badge';
                    } else {
                        statusEl.textContent = `${remaining} mağaza takipte`;
                    }
                } catch (err) {
                    alert('Hata: ' + err.message);
                }
            });
        });

    } catch (e) {
        statusEl.textContent = 'Yükleme hatası';
        statusEl.className = 'badge badge-error';
        console.error(e);
    }
}

async function toggleDashListings(magazaId, card, listingsDiv, onCountChange) {
    const isOpen = !listingsDiv.classList.contains('hidden');
    if (isOpen) { listingsDiv.classList.add('hidden'); return; }

    listingsDiv.classList.remove('hidden');
    if (listingsDiv.dataset.loaded === '1') return;

    listingsDiv.innerHTML = '<div class="listings-loading">Ürünler yükleniyor...</div>';
    try {
        const listinglar = await api.magazaListingleri(magazaId);
        renderMagazaListingleri(listingsDiv, card, listinglar, onCountChange);
        listingsDiv.dataset.loaded = '1';
    } catch (e) {
        listingsDiv.innerHTML = '<p class="text-muted" style="padding:1rem">Yükleme hatası.</p>';
    }
}

// ─── Yardımcılar ──────────────────────────────────────────────────────────

function setStatus(id, text, type = '') {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    el.className = 'badge' + (type ? ' badge-' + type : '');
}

function bekle(ms) {
    return new Promise(r => setTimeout(r, ms));
}

function escapeHtml(str) {
    return String(str ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function escapeAttr(str) {
    return escapeHtml(str);
}

function formatShortDate(isoDate) {
    if (!isoDate) return '';
    const parts = String(isoDate).split('-');
    if (parts.length !== 3) return isoDate;
    const aylar = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara'];
    const ayIdx = parseInt(parts[1], 10) - 1;
    return `${parseInt(parts[2], 10)} ${aylar[ayIdx] || parts[1]}`;
}
