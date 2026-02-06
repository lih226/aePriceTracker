// AE Price Tracker - Frontend JavaScript

// State
let currentProduct = null;
let productToDelete = null;
let priceChart = null;
let currentUser = null; // Logged-in user info

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

document.addEventListener('DOMContentLoaded', async () => {
    // Read auth state from body data attributes (set by server)
    const isAuthenticated = document.body.dataset.authenticated === 'true';
    const userEmail = document.body.dataset.userEmail;



    if (isAuthenticated && userEmail) {
        currentUser = { email: userEmail };

        // Logged-in users: load products from server (synced across devices)
        await loadServerProducts();
    } else {

        // Guest users: load products from localStorage
        loadLocalProducts();
    }

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
        if (currentUser) {

            // Logged-in users: save to server for cross-device sync
            const response = await fetch('/api/track', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Failed to track product');
            }

            // Add to local serverProducts array and re-render
            const product = data.product;
            serverProducts.push(product);
            currentProduct = product;
            displayProduct(currentProduct);
            renderServerProductsList();
            showToast('Product tracked and synced to your account!', 'success');

        } else {
            // Guest users: save to localStorage only
            const response = await fetch('/api/scrape', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Failed to track product');
            }

            const product = {
                url: url,
                ...data // name, current_price, list_price, image_url
            };

            const savedProduct = Storage.saveProduct(product);
            currentProduct = savedProduct;
            displayProduct(currentProduct);
            renderProductsList();
            showToast('Product tracked locally!', 'success');
        }

        urlInput.value = '';

    } catch (error) {
        showToast(error.message, 'error');
    } finally {
        setLoading(false);
    }
}

async function refreshProduct(productId) {
    // 1. Identify product from either global state or local storage
    let product = currentUser
        ? serverProducts.find(p => p.id == productId)
        : Storage.getProduct(productId);

    // Fallback to currentProduct if details modal is open
    if (!product && currentProduct && currentProduct.id == productId) {
        product = currentProduct;
    }

    if (!product) {
        console.error('Refresh failed: Product not found', productId);
        showToast('Could not find product to refresh', 'error');
        return;
    }

    if (product.is_available === false) {
        showToast('Cannot refresh unavailable product', 'warning');
        return;
    }

    // 2. UI Loading State
    const refreshBtn = document.getElementById('refreshBtn');
    const originalText = refreshBtn.innerHTML;
    refreshBtn.disabled = true;
    refreshBtn.innerHTML = '<span class="btn-loader"></span> Refreshing...';

    try {
        let updated;
        if (currentUser) {
            // Path A: Authenticated user - Sync with server
            const response = await fetch(`/api/refresh/${productId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            const data = await response.json();

            if (!response.ok) throw new Error(data.error || 'Server refresh failed');

            updated = data.product;

            // Update the global serverProducts list
            const idx = serverProducts.findIndex(p => p.id == productId);
            if (idx >= 0) {
                serverProducts[idx] = updated;
            } else {
                serverProducts.push(updated);
            }

            // Re-render the list
            renderServerProductsList();
        } else {
            // Path B: Guest user - Scrape locally and update localStorage
            const response = await fetch('/api/scrape', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: product.url })
            });
            const data = await response.json();

            if (!response.ok) throw new Error(data.error || 'Scrape failed');

            updated = Storage.updateProduct(productId, {
                current_price: data.current_price,
                list_price: data.list_price,
                is_available: data.is_available,
                last_checked: new Date().toISOString()
            });

            // Re-render the local list
            renderProductsList();
        }

        // 3. Update active display if looking at this product
        if (currentProduct && currentProduct.id == productId) {
            currentProduct = updated;
            displayProduct(currentProduct);
        }

        showToast('Status updated!', 'success');

    } catch (error) {
        console.error('Refresh error:', error);
        showToast(error.message, 'error');
    } finally {
        refreshBtn.disabled = false;
        refreshBtn.innerHTML = originalText;
    }
}



async function saveAlert() {

    const targetPrice = document.getElementById('targetPrice').value;
    const emailInput = document.getElementById('alertEmail');
    const email = emailInput.value.trim();

    if (!targetPrice) {
        showToast('Please set a target price', 'error');
        return;
    }

    // Only require email input if user is not logged in
    if (!currentUser && !email) {
        showToast('Please enter your email address for alerts', 'error');
        emailInput.focus();
        return;
    }

    const saveBtn = document.getElementById('saveAlertBtn');
    const originalText = saveBtn.textContent;
    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving...';

    try {
        // 1. Ensure product exists on server to get a real DB ID
        const trackResponse = await fetch('/api/track', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: currentProduct.url })
        });

        if (!trackResponse.ok) {
            let errorMsg = 'Failed to sync product with server';
            try {
                const err = await trackResponse.json();
                errorMsg = err.error || errorMsg;
            } catch (e) {
                errorMsg = `Server error (${trackResponse.status})`;
            }
            throw new Error(errorMsg);
        }
        const trackData = await trackResponse.json();
        const serverProductId = trackData.product.id;

        // 2. Create/Update alert on server
        const alertResponse = await fetch('/api/alert', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                product_id: serverProductId,
                email: email,
                target_price: targetPrice
            })
        });

        if (!alertResponse.ok) {
            let errorMsg = 'Failed to create alert';
            try {
                const err = await alertResponse.json();
                errorMsg = err.error || errorMsg;
            } catch (e) {
                errorMsg = `Server error (${alertResponse.status})`;
            }
            throw new Error(errorMsg);
        }

        const alertData = await alertResponse.json();
        const updatedAlert = alertData.alert;

        // 3. Update state (Local vs Server)
        if (currentUser) {

            // Find in serverProducts array and update
            const idx = serverProducts.findIndex(p => p.id === serverProductId);
            if (idx !== -1) {
                serverProducts[idx].alert_target = parseFloat(targetPrice);
                serverProducts[idx].alert_email = email;
                // Also update alerts array if present
                if (!serverProducts[idx].alerts) serverProducts[idx].alerts = [];
                // Add or replace alert
                serverProducts[idx].alerts = serverProducts[idx].alerts.filter(a => a.triggered); // remove active ones
                serverProducts[idx].alerts.push(updatedAlert);
            }
            renderServerProductsList();
        } else {
            // Update local storage metadata for guest
            Storage.updateProduct(currentProduct.id, {
                alert_target: parseFloat(targetPrice),
                alert_email: email,
                server_id: serverProductId,
                alert_token: updatedAlert.token // Persist token for guest
            });
            renderProductsList();
        }

        showToast('Price alert saved! We\'ll email you when the price drops.', 'success');
        closeAlertModal();

    } catch (error) {
        showToast(error.message, 'error');
        console.error('Alert error:', error);
    } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = originalText;
    }
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

// Server product helper functions for logged-in users
function viewServerProduct(productId) {
    const product = serverProducts.find(p => p.id === productId);
    if (product) {
        // Add alert info from product.alerts if available
        if (product.alerts && product.alerts.length > 0) {
            const activeAlert = product.alerts.find(a => !a.triggered);
            if (activeAlert) {
                product.alert_target = activeAlert.target_price;
                product.alert_email = activeAlert.email;
            }
        }
        currentProduct = product;
        displayProduct(currentProduct);
        productDisplay.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } else {
        showToast('Product not found', 'error');
    }
}

function openAlertForServerProduct(productId) {
    const product = serverProducts.find(p => p.id === productId);
    if (product) {
        currentProduct = product;
        openAlertModal();
    }
}

async function deleteServerProduct(productId) {
    try {
        const response = await fetch(`/api/product/${productId}`, {
            method: 'DELETE'
        });
        if (response.ok) {
            serverProducts = serverProducts.filter(p => p.id !== productId);
            renderServerProductsList();
            showToast('Product removed', 'success');

            // Hide details if open
            if (currentProduct && currentProduct.id === productId) {
                productDisplay.hidden = true;
                currentProduct = null;
            }
        } else {
            showToast('Failed to remove product', 'error');
        }
    } catch (error) {
        showToast('Error removing product', 'error');
    }
}

// ============ UI Functions ============

// Server-synced products for logged-in users
let serverProducts = [];

async function loadServerProducts() {
    try {
        const response = await fetch('/api/user/products');
        if (response.ok) {
            serverProducts = await response.json();
            renderServerProductsList();
        } else {
            showToast('Failed to load synced products', 'error');
            loadLocalProducts(); // Fallback to local
        }
    } catch (error) {
        console.error('Error loading server products:', error);
        loadLocalProducts(); // Fallback to local
    }
}

function renderServerProductsList() {
    productsList.innerHTML = '';

    if (serverProducts.length === 0) {
        productsList.innerHTML = '<p class="empty-message">No products tracked yet. Add your first product above!</p>';
        return;
    }

    serverProducts.forEach(product => {
        const card = createProductCard(product, true); // true = server product
        productsList.appendChild(card);
    });
}

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
        const card = createProductCard(product, false); // false = local product
        productsList.appendChild(card);
    });
}

// Shared product card creation for both local and server products
function createProductCard(product, isServerProduct) {
    const card = document.createElement('div');
    const isUnavailable = product.is_available === false;
    card.className = `product-card glass-card ${isUnavailable ? 'unavailable' : ''}`;
    card.dataset.id = product.id;
    card.onclick = () => {
        if (isUnavailable) {
            showToast('This product is currently unavailable', 'warning');
        }
        isServerProduct ? viewServerProduct(product.id) : viewProduct(product.id);
    };

    // Calculate visuals
    const isOnSale = product.list_price && product.current_price < product.list_price;
    const discount = isOnSale ? Math.round((1 - product.current_price / product.list_price) * 100) : 0;
    const lastChecked = product.last_checked ? formatDate(product.last_checked) : 'Never';
    const image = product.image_url || '/static/placeholder.png';
    const price = product.current_price ? `$${product.current_price.toFixed(2)}` : 'N/A';

    let saleHtml = '';
    if (isOnSale) {
        saleHtml = `
            <span class="card-list-price">$${product.list_price.toFixed(2)}</span>
            <span class="card-discount">-${discount}%</span>
        `;
    }

    // For server products, alerts are always synced (logged-in user)
    const hasAlert = isServerProduct
        ? (product.alerts && product.alerts.some(a => !a.triggered))
        : (product.alert_target > 0);
    const alertClass = hasAlert ? 'active alert-synced' : '';

    card.innerHTML = `
        <div class="card-image-container">
            ${isUnavailable ? '<span class="status-badge">Unavailable</span>' : ''}
            <button class="btn-card-alert ${alertClass}"
                ${isUnavailable ? 'disabled' : ''}
                onclick="event.stopPropagation(); ${isServerProduct ? `openAlertForServerProduct(${product.id})` : `openAlertForProduct('${product.id}')`}"
                title="${isUnavailable ? 'Product Unavailable' : (hasAlert ? 'Alert active' : 'Set Price Alert')}">
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
                onclick="event.stopPropagation(); ${isServerProduct ? `deleteServerProduct(${product.id})` : `openDeleteModal('${product.id}')`}">🗑️</button>
        </div>
    `;

    return card;
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

    const setAlertBtn = document.getElementById('setAlertBtn');
    const refreshBtn = document.getElementById('refreshBtn');

    if (product.is_available === false) {
        setAlertBtn.disabled = true;
        setAlertBtn.title = 'Product is currently unavailable';
        refreshBtn.disabled = true;
        refreshBtn.title = 'Cannot refresh unavailable product';
        document.getElementById('currentPrice').style.color = 'var(--text-muted)';
        document.getElementById('productName').innerHTML = `${product.name} <small style="color: var(--accent-danger); font-size: 0.8rem;">(UNAVAILABLE)</small>`;
    } else {
        setAlertBtn.disabled = false;
        setAlertBtn.title = 'Set Price Alert';
        refreshBtn.disabled = false;
        refreshBtn.title = 'Refresh product status';
        document.getElementById('currentPrice').style.color = '';
        document.getElementById('productName').textContent = product.name;
    }

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

    // Set values
    const targetPriceInput = document.getElementById('targetPrice');
    const emailInput = document.getElementById('alertEmail');
    const removeBtn = document.getElementById('removeAlertBtn');

    // If tracking as server product (logged in), use product.alert_target
    // If tracking locally, use currentProduct.alert_target

    targetPriceInput.value = currentProduct.alert_target || '';
    if (currentUser) {
        // Email is readonly/hidden input, handled by template
    } else {
        emailInput.value = currentProduct.alert_email || '';
    }

    // Show/Hide Unsubscribe button if alert exists
    // For logged-in users, find token in alerts array
    // For guests, use alert_token from storage
    let token = null;
    if (currentUser) {
        const activeAlert = (currentProduct.alerts || []).find(a => !a.triggered);
        token = activeAlert ? activeAlert.token : null;
    } else {
        token = currentProduct.alert_token;
    }

    if (token) {
        removeBtn.hidden = false;
        removeBtn.onclick = () => {
            window.location.href = `/unsubscribe/${token}`;
        };
    } else {
        removeBtn.hidden = true;
    }

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

