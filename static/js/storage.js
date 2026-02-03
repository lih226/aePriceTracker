/**
 * Local Storage Management for AE Price Tracker
 * Handles saving, retrieving, and updating tracked products in the browser.
 */

const STORAGE_KEY = 'ae_tracker_products';

const Storage = {
    /**
     * Get all tracked products
     * @returns {Array} List of product objects
     */
    getProducts: () => {
        const stored = localStorage.getItem(STORAGE_KEY);
        return stored ? JSON.parse(stored) : [];
    },

    /**
     * Save a new product or update existing one
     * @param {Object} product - Product object to save
     */
    saveProduct: (product) => {
        const products = Storage.getProducts();

        // Check if exists
        const index = products.findIndex(p => p.url === product.url);

        if (index >= 0) {
            // Update existing
            products[index] = { ...products[index], ...product };
        } else {
            // Add new
            // Generate a local ID if not present (to mimic DB ID for UI logic)
            if (!product.id) {
                product.id = Date.now().toString(36) + Math.random().toString(36).substr(2);
            }
            // Add added_at timestamp if missing
            if (!product.added_at) {
                product.added_at = new Date().toISOString();
            }
            // Add last_checked if missing (for new products)
            if (!product.last_checked) {
                product.last_checked = new Date().toISOString();
            }
            // Initialize price history array if missing
            if (!product.price_history) {
                product.price_history = [];
            }
            // Add current price to history if it's new
            if (product.current_price) {
                product.price_history.push({
                    price: product.current_price,
                    timestamp: new Date().toISOString()
                });
            }

            products.unshift(product); // Add to top
        }

        localStorage.setItem(STORAGE_KEY, JSON.stringify(products));
        return product;
    },

    /**
     * Update a specific product by ID
     * @param {String} id - Product ID
     * @param {Object} updates - Fields to update
     */
    updateProduct: (id, updates) => {
        const products = Storage.getProducts();
        const index = products.findIndex(p => p.id === id);

        if (index >= 0) {
            // Check if price changed to record history
            if (updates.current_price && updates.current_price !== products[index].current_price) {
                if (!products[index].price_history) products[index].price_history = [];

                products[index].price_history.push({
                    price: updates.current_price,
                    timestamp: new Date().toISOString()
                });
            }

            products[index] = { ...products[index], ...updates };
            localStorage.setItem(STORAGE_KEY, JSON.stringify(products));
            return products[index];
        }
        return null;
    },

    /**
     * Delete a product
     * @param {String} id - Product ID
     */
    deleteProduct: (id) => {
        const products = Storage.getProducts();
        const filtered = products.filter(p => p.id !== id);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(filtered));
    },

    /**
     * Get a single product by ID
     * @param {String} id 
     */
    getProduct: (id) => {
        const products = Storage.getProducts();
        return products.find(p => p.id === id);
    }
};
