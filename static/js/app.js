// AE Price Tracker - Frontend JavaScript

// State
let currentProduct = null;
let productToDelete = null;
let priceChart = null;

// DOM Elements
const trackForm = document.getElementById('trackForm');
const urlInput = document.getElementById('urlInput');
const trackBtn = document.getElementById('trackBtn');
const productDisplay = document.getElementById('productDisplay');
const alertModal = document.getElementById('alertModal');
const deleteModal = document.getElementById('deleteModal');
const toast = document.getElementById('toast');
const productsList = document.getElementById('productsList');

// ============ Event Listeners ============

document.addEventListener('DOMContentLoaded', () => {
    loadLocalProducts();
    // refreshAllPrices(); // Disabled: Only refresh on user request or daily job
});

trackForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    await trackProduct(urlInput.value);
});

document.getElementById('setAlertBtn').addEventListener('click', () => {
    openAlertModal();
});

document.getElementById('refreshBtn').addEventListener('click', async () => {
    if (currentProduct) {
        await refreshProduct(currentProduct.id);
    }
});

document.getElementById('cancelAlertBtn').addEventListener('click', () => {
    closeAlertModal();
});

document.getElementById('saveAlertBtn').addEventListener('click', async () => {
    await saveAlert();
});

document.getElementById('closeProductBtn').addEventListener('click', () => {
    productDisplay.hidden = true;
    currentProduct = null;
});

// Close modals on overlay click
document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', () => {
        closeAlertModal();
        if (typeof closeDeleteModal === 'function') closeDeleteModal();
    });
});

document.getElementById('cancelDeleteBtn')?.addEventListener('click', () => {
    if (typeof closeDeleteModal === 'function') closeDeleteModal();
});

document.getElementById('confirmDeleteBtn')?.addEventListener('click', () => {
    if (productToDelete) {
        deleteProduct(productToDelete);
    }
});

// ============ API & Storage Functions ============

async function trackProduct(url) {
    setLoading(true);

    try {
        // 1. Scrape data from server (stateless)
        const response = await fetch('/api/scrape', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to track product');
        }

        // 2. Save to Local Storage
        const product = {
            url: url,
            ...data // name, current_price, list_price, image_url
        };

        const savedProduct = Storage.saveProduct(product);

        // 3. Update UI
        currentProduct = savedProduct;
        displayProduct(currentProduct);
        showToast('Product tracked locally!', 'success');
        urlInput.value = '';

        renderProductsList(); // Re-render list from local storage

    } catch (error) {
        showToast(error.message, 'error');
    } finally {
        setLoading(false);
    }
}

async function refreshProduct(productId) {
    const product = Storage.getProduct(productId);
    if (!product) return;

    // UI feedback
    const refreshBtn = document.getElementById('refreshBtn');
    const originalText = refreshBtn.innerHTML;
    refreshBtn.disabled = true;
    refreshBtn.innerHTML = '<span class="btn-loader"></span> Refreshing...';

    try {
        const response = await fetch('/api/scrape', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: product.url })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to refresh price');
        }

        // Update local storage
        const updated = Storage.updateProduct(productId, {
            current_price: data.current_price,
            list_price: data.list_price,
            last_checked: new Date().toISOString()
        });

        currentProduct = updated;
        displayProduct(currentProduct);
        renderProductsList(); // Update card in list
        showToast('Price updated!', 'success');

    } catch (error) {
        showToast(error.message, 'error');
    } finally {
        refreshBtn.disabled = false;
        refreshBtn.innerHTML = originalText;
    }
}

async function refreshAllPrices() {
    const products = Storage.getProducts();
    if (products.length === 0) return;

    console.log("Auto-refreshing prices...");

    for (const product of products) {
        try {
            const response = await fetch('/api/scrape', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: product.url })
            });

            if (response.ok) {
                const data = await response.json();
                Storage.updateProduct(product.id, {
                    current_price: data.current_price,
                    list_price: data.list_price,
                    last_checked: new Date().toISOString()
                });
            }
        } catch (e) {
            console.error("Failed to auto-refresh", product.name, e);
        }
    }
    renderProductsList();
}

async function saveAlert() {
    // Local alert logic (placeholder for now, or sync with server if user authenticated)
    // For anonymous users, we can't send emails easily without backend storage.
    // OPTION: We could send the alert config to server to store in a 'guest_alerts' table,
    // but the prompt asked for localStorage focus. 
    // For now, let's just save the target price locally and visually indicate it.

    const targetPrice = document.getElementById('targetPrice').value;
    const email = document.getElementById('alertEmail').value.trim(); // We might collect this but not use it yet for pure local

    if (!targetPrice) {
        showToast('Please set a target price', 'error');
        return;
    }

    // Save alert settings locally
    Storage.updateProduct(currentProduct.id, {
        alert_target: parseFloat(targetPrice),
        alert_email: email // Stored locally for now
    });

    showToast('Alert saved locally (Email notifications require login - coming soon)', 'success');
    closeAlertModal();
    renderProductsList();
}

function deleteProduct(productId) {
    if (typeof closeDeleteModal === 'function') closeDeleteModal();

    Storage.deleteProduct(productId);
    showToast('Product removed', 'success');

    // Hide details if open
    if (currentProduct && currentProduct.id === productId) {
        productDisplay.hidden = true;
        currentProduct = null;
    }

    renderProductsList();
}

function viewProduct(productId) {
    // productId might be string or number depending on generation
    // Ensure we match types (Storage IDs are strings usually)
    const product = Storage.getProduct(String(productId));

    if (product) {
        currentProduct = product;
        displayProduct(currentProduct);
        productDisplay.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } else {
        showToast('Product not found', 'error');
    }
}

function openAlertForProduct(productId) {
    const product = Storage.getProduct(String(productId));
    if (product) {
        currentProduct = product;
        openAlertModal();
    }
}

// ============ UI Functions ============

function loadLocalProducts() {
    renderProductsList();
}

function renderProductsList() {
    const products = Storage.getProducts();
    productsList.innerHTML = '';

    if (products.length === 0) {
        productsList.innerHTML = '<p class="empty-message">No products tracked yet. Add your first product above!</p>';
        return;
    }

    products.forEach(product => {
        const card = document.createElement('div');
        card.className = 'product-card glass-card';
        card.dataset.id = product.id;
        card.onclick = () => viewProduct(product.id);

        // Calculate visuals
        const isOnSale = product.list_price && product.current_price < product.list_price;
        const discount = isOnSale ? Math.round((1 - product.current_price / product.list_price) * 100) : 0;
        const lastChecked = product.last_checked ? timeAgo(new Date(product.last_checked)) : 'Never';
        const image = product.image_url || '/static/placeholder.png';
        const price = product.current_price ? `$${product.current_price.toFixed(2)}` : 'N/A';

        let saleHtml = '';
        if (isOnSale) {
            saleHtml = `
                <span class="card-list-price">$${product.list_price.toFixed(2)}</span>
                <span class="card-discount">-${discount}%</span>
            `;
        }

        // Alert indication
        const hasAlert = product.alert_target > 0;
        const alertClass = hasAlert ? 'active' : '';

        card.innerHTML = `
            <div class="card-image-container">
                <button class="btn-card-alert ${alertClass}"
                    onclick="event.stopPropagation(); openAlertForProduct('${product.id}')"
                    title="Set Price Alert">
                    <svg class="icon-bell" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                        stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path>
                        <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
                    </svg>
                </button>
                <img src="${image}" alt="${product.name}" class="card-image">
            </div>
            <div class="card-content">
                <h4 class="card-title">${product.name}</h4>
                <div class="card-price-row">
                    <span class="card-price">${price}</span>
                    ${saleHtml}
                </div>
                <p class="card-checked">Last checked: <span class="local-date">${lastChecked}</span></p>
            </div>
            <div class="card-actions">
                <button class="btn-view">View Details</button>
                <button class="btn-delete"
                    onclick="event.stopPropagation(); openDeleteModal('${product.id}')">🗑️</button>
            </div>
        `;

        productsList.appendChild(card);
    });
}

function formatDate(utcString) {
    if (!utcString) return 'Never';
    let dateStr = utcString.replace(' ', 'T');
    if (!dateStr.includes('Z') && !dateStr.includes('+')) {
        dateStr += 'Z';
    }
    const date = new Date(dateStr);
    return timeAgo(date);
}

function timeAgo(date) {
    const seconds = Math.floor((new Date() - date) / 1000);
    if (seconds < 30) return 'Just now';
    if (seconds < 60) return seconds + 's ago';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return minutes + 'm ago';
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return hours + 'h ago';
    const days = Math.floor(hours / 24);
    if (days < 30) return days + 'd ago';
    return date.toLocaleDateString();
}

function displayProduct(product) {
    document.getElementById('productName').textContent = product.name;
    document.getElementById('currentPrice').textContent = product.current_price
        ? `$${product.current_price.toFixed(2)}`
        : 'N/A';

    const listPriceElem = document.getElementById('listPrice');
    const discountBadgeElem = document.getElementById('discountBadge');

    const isOnSale = product.list_price && product.current_price < product.list_price;

    if (isOnSale) {
        const discount = Math.round((1 - product.current_price / product.list_price) * 100);
        listPriceElem.textContent = `$${product.list_price.toFixed(2)}`;
        listPriceElem.hidden = false;
        discountBadgeElem.textContent = `-${discount}%`;
        discountBadgeElem.hidden = false;
    } else {
        listPriceElem.hidden = true;
        discountBadgeElem.hidden = true;
    }

    document.getElementById('productImage').src = product.image_url || '/static/placeholder.png';
    document.getElementById('productLink').href = product.url;

    const lastChecked = product.last_checked ? formatDate(product.last_checked) : 'Never';
    document.getElementById('lastChecked').textContent = `Last checked: ${lastChecked}`;

    productDisplay.hidden = false;

    // Update chart
    updateChart(product.price_history || []);
}

function updateChart(priceHistory) {
    if (!priceHistory) return;

    const ctx = document.getElementById('priceChart').getContext('2d');
    if (priceChart) priceChart.destroy();

    const labels = priceHistory.map(p => {
        const date = new Date(p.timestamp);
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    });

    const prices = priceHistory.map(p => p.price);
    const gradient = ctx.createLinearGradient(0, 0, 0, 300);
    gradient.addColorStop(0, 'rgba(59, 130, 246, 0.3)');
    gradient.addColorStop(1, 'rgba(59, 130, 246, 0)');

    priceChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label: 'Price',
                data: prices,
                borderColor: '#3b82f6',
                backgroundColor: gradient,
                borderWidth: 3,
                fill: true,
                tension: 0.4,
                pointBackgroundColor: '#3b82f6',
                pointBorderColor: '#fff',
                pointBorderWidth: 2,
                pointRadius: 5,
                pointHoverRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(15, 15, 26, 0.9)',
                    titleColor: '#f8fafc',
                    bodyColor: '#94a3b8',
                    borderColor: 'rgba(255, 255, 255, 0.1)',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: false,
                    callbacks: {
                        label: (context) => context.raw != null ? `$${context.raw.toFixed(2)}` : 'N/A'
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#64748b' }
                },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: {
                        color: '#64748b',
                        callback: (value) => `$${Number(value).toFixed(2)}`
                    }
                }
            }
        }
    });
}

function openAlertModal() {
    document.getElementById('modalCurrentPrice').textContent = currentProduct.current_price
        ? `$${currentProduct.current_price.toFixed(2)}`
        : 'N/A';
    document.getElementById('targetPrice').value = currentProduct.alert_target || '';
    document.getElementById('alertEmail').value = currentProduct.alert_email || '';
    alertModal.hidden = false;
}

function closeAlertModal() {
    alertModal.hidden = true;
}

function setLoading(loading) {
    const btnText = trackBtn.querySelector('.btn-text');
    const btnLoader = trackBtn.querySelector('.btn-loader');

    trackBtn.disabled = loading;
    btnText.hidden = loading;
    btnLoader.hidden = !loading;
}

function showToast(message, type = 'info') {
    toast.textContent = message;
    toast.className = `toast ${type}`;
    toast.hidden = false;
    requestAnimationFrame(() => {
        toast.classList.add('show');
    });
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => {
            toast.hidden = true;
        }, 300);
    }, 4000);
}

// Make functions globally accessible
window.viewProduct = viewProduct;
window.deleteProduct = deleteProduct;
window.openAlertForProduct = openAlertForProduct;

function openDeleteModal(productId) {
    productToDelete = productId;
    if (deleteModal) deleteModal.hidden = false;
}

function closeDeleteModal() {
    if (deleteModal) deleteModal.hidden = true;
    productToDelete = null;
}

window.openDeleteModal = openDeleteModal;

