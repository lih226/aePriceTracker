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

// ============ Event Listeners ============

document.addEventListener('DOMContentLoaded', () => {
    // Convert all server-rendered UTC dates to user-friendly relative time
    document.querySelectorAll('.local-date').forEach(el => {
        const utc = el.dataset.utc;
        if (utc) {
            el.textContent = formatDate(utc);
        }
    });
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

// ============ API Functions ============

async function trackProduct(url) {
    setLoading(true);

    try {
        const response = await fetch('/api/track', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to track product');
        }

        currentProduct = data.product;
        displayProduct(currentProduct);
        showToast(data.message, 'success');
        urlInput.value = '';

        // Reload page to update products list
        setTimeout(() => location.reload(), 1500);

    } catch (error) {
        showToast(error.message, 'error');
    } finally {
        setLoading(false);
    }
}

async function refreshProduct(productId) {
    try {
        const response = await fetch(`/api/refresh/${productId}`, {
            method: 'POST'
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to refresh price');
        }

        currentProduct = data.product;
        displayProduct(currentProduct);
        updateProductCard(currentProduct);
        showToast('Price updated!', 'success');

    } catch (error) {
        showToast(error.message, 'error');
    }
}

async function saveAlert() {
    const email = document.getElementById('alertEmail').value.trim();
    const targetPrice = document.getElementById('targetPrice').value;

    if (!email || !targetPrice) {
        showToast('Please fill in all fields', 'error');
        return;
    }

    try {
        const response = await fetch('/api/alert', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                product_id: currentProduct.id,
                email,
                target_price: parseFloat(targetPrice)
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to create alert');
        }

        showToast('Price alert saved! We\'ll email you when the price drops.', 'success');
        closeAlertModal();

    } catch (error) {
        showToast(error.message, 'error');
    }
}

async function deleteProduct(productId) {
    if (typeof closeDeleteModal === 'function') closeDeleteModal();

    try {
        const response = await fetch(`/api/product/${productId}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            throw new Error('Failed to delete product');
        }

        showToast('Product deleted', 'success');

        // Remove card from DOM
        const card = document.querySelector(`.product-card[data-id="${productId}"]`);
        if (card) {
            card.remove();
        }

        // Hide product display if it's the current one
        if (currentProduct && currentProduct.id === productId) {
            productDisplay.hidden = true;
            currentProduct = null;
        }

    } catch (error) {
        showToast(error.message, 'error');
    }
}

async function viewProduct(productId) {
    try {
        const response = await fetch(`/api/product/${productId}`);
        const data = await response.json();

        if (!response.ok) {
            throw new Error('Failed to load product');
        }

        currentProduct = data;
        displayProduct(currentProduct);

        // Scroll to product display
        productDisplay.scrollIntoView({ behavior: 'smooth', block: 'start' });

    } catch (error) {
        showToast(error.message, 'error');
    }
}

async function openAlertForProduct(productId) {
    try {
        const response = await fetch(`/api/product/${productId}`);
        const data = await response.json();

        if (!response.ok) {
            throw new Error('Failed to load product');
        }

        currentProduct = data;
        openAlertModal();

    } catch (error) {
        showToast(error.message, 'error');
    }
}

// ============ UI Functions ============

function formatDate(utcString) {
    if (!utcString) return 'Never';

    // Force UTC by ensuring the string looks like an ISO UTC string (adding Z)
    // Python's isoformat() might be 2026-01-30T20:10:04 or 2026-01-30 20:10:04
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

function updateProductCard(product) {
    const card = document.querySelector(`.product-card[data-id="${product.id}"]`);
    if (!card) return;

    const priceElem = card.querySelector('.card-price');
    const rowElem = card.querySelector('.card-price-row');
    const checkedElem = card.querySelector('.card-checked');

    if (priceElem) {
        priceElem.textContent = product.current_price
            ? `$${product.current_price.toFixed(2)}`
            : 'N/A';
    }

    // Update sale info in card
    if (product.is_on_sale) {
        // Remove existing if any (to re-add in order)
        const oldList = rowElem.querySelector('.card-list-price');
        const oldDisc = rowElem.querySelector('.card-discount');
        if (oldList) oldList.remove();
        if (oldDisc) oldDisc.remove();

        const listSpan = document.createElement('span');
        listSpan.className = 'card-list-price';
        listSpan.textContent = `$${product.list_price.toFixed(2)}`;

        const discSpan = document.createElement('span');
        discSpan.className = 'card-discount';
        discSpan.textContent = `-${product.discount_percentage}%`;

        rowElem.appendChild(listSpan);
        rowElem.appendChild(discSpan);
    } else {
        const oldList = rowElem.querySelector('.card-list-price');
        const oldDisc = rowElem.querySelector('.card-discount');
        if (oldList) oldList.remove();
        if (oldDisc) oldDisc.remove();
    }

    if (checkedElem) {
        const dateSpan = checkedElem.querySelector('.local-date');
        const lastChecked = formatDate(product.last_checked);

        if (dateSpan) {
            dateSpan.textContent = lastChecked;
            dateSpan.dataset.utc = product.last_checked || '';
        } else {
            checkedElem.textContent = `Last checked: ${lastChecked}`;
        }
    }
}

function displayProduct(product) {
    document.getElementById('productName').textContent = product.name;
    document.getElementById('currentPrice').textContent = product.current_price
        ? `$${product.current_price.toFixed(2)}`
        : 'N/A';

    const listPriceElem = document.getElementById('listPrice');
    const discountBadgeElem = document.getElementById('discountBadge');

    if (product.is_on_sale) {
        listPriceElem.textContent = `$${product.list_price.toFixed(2)}`;
        listPriceElem.hidden = false;
        discountBadgeElem.textContent = `-${product.discount_percentage}%`;
        discountBadgeElem.hidden = false;
    } else {
        listPriceElem.hidden = true;
        discountBadgeElem.hidden = true;
    }

    document.getElementById('productImage').src = product.image_url || '/static/placeholder.png';
    document.getElementById('productLink').href = product.url;

    const lastChecked = formatDate(product.last_checked);
    document.getElementById('lastChecked').textContent = `Last checked: ${lastChecked}`;

    productDisplay.hidden = false;

    // Update chart
    updateChart(product.price_history);
}

function updateChart(priceHistory) {
    const ctx = document.getElementById('priceChart').getContext('2d');

    // Destroy existing chart
    if (priceChart) {
        priceChart.destroy();
    }

    // Prepare data
    const labels = priceHistory.map(p => {
        const date = new Date(p.timestamp);
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    });

    const prices = priceHistory.map(p => p.price);

    // Create gradient
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
    document.getElementById('targetPrice').value = '';
    document.getElementById('alertEmail').value = '';
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

    // Trigger animation
    requestAnimationFrame(() => {
        toast.classList.add('show');
    });

    // Hide after 4 seconds
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
