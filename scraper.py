# Price Scraper Service
import requests
from bs4 import BeautifulSoup
import json
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def fetch_product_data(url):
    """
    Fetch product data from American Eagle website.
    Uses multiple methods to extract product info.
    Returns dict with name, price, and image_url or None if failed.
    """
    # Extract product ID from URL
    product_id = extract_product_id(url)
    
    if product_id:
        # Try API endpoint first (most reliable)
        api_data = fetch_from_api(product_id)
        if api_data:
            return api_data
    
    # Fallback: Try scraping the page directly
    return scrape_page(url, product_id)


def extract_product_id(url):
    """Extract product ID from American Eagle URL"""
    # URL format: .../0577_9098_900 or .../0577-9098-900
    patterns = [
        r'/(\d{4}_\d{4}_\d{3})',  # underscore format
        r'/(\d{4}-\d{4}-\d{3})',  # dash format
        r'productId=(\d+)',       # query parameter
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1).replace('-', '_')
    
    return None


def fetch_from_api(product_id):
    """Fetch product data from AE's internal API"""
    try:
        # AE uses a product detail API
        api_url = f"https://www.ae.com/ugp-api/prod/products/v2/color/{product_id}"
        
        api_headers = {
            **HEADERS,
            "Accept": "application/json",
            "x-ae-channel": "web",
        }
        
        response = requests.get(api_url, headers=api_headers, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            
            # Extract product info from API response
            name = data.get('productName') or data.get('name')
            
            # Extract prices from API response
            # AE API levels: salePrice, listPrice, or pricing object
            sale_price = data.get('sale_price') or data.get('salePrice')
            list_price = data.get('list_price') or data.get('listPrice') or data.get('price')
            
            if 'pricing' in data:
                pricing = data['pricing']
                sale_price = sale_price or pricing.get('salePrice') or pricing.get('sale_price')
                list_price = list_price or pricing.get('listPrice') or pricing.get('list_price') or pricing.get('price')
            
            # Check variants in API response as well
            if 'variants' in data and len(data['variants']) > 0:
                for v in data['variants']:
                    vs = v.get('salePrice') or v.get('sale_price')
                    vl = v.get('listPrice') or v.get('list_price')
                    if vl:
                        list_price = max(float(list_price) if list_price else 0, float(vl))
                    if vs:
                        sale_price = vs if not sale_price or float(vs) < float(sale_price) else sale_price

            # Convert to float
            current_price = float(sale_price) if sale_price is not None else None
            list_price = float(list_price) if list_price is not None else current_price
            
            # If no current_price but we have list_price, use list_price
            if current_price is None and list_price is not None:
                current_price = list_price
            
            # Ensure list_price is at least current_price
            if list_price is not None and current_price is not None and list_price < current_price:
                list_price = current_price
            
            # Get image
            image_url = None
            if 'productImage' in data:
                image_url = data['productImage']
            elif 'images' in data and len(data['images']) > 0:
                image_url = data['images'][0].get('url')
            
            if name:
                # Check multiple flags, if any are True, assume available. 
                # Only trust False if multiple signals or high-confidence ones say so.
                is_available = True
                flags = [data.get('isAvailable'), data.get('inStock'), data.get('isOrderable'), data.get('buyable')]
                # Filter out None values
                provided_flags = [f for f in flags if f is not None]
                if provided_flags:
                    is_available = any(provided_flags)

                return {
                    'name': name,
                    'current_price': current_price,
                    'list_price': list_price,
                    'image_url': image_url,
                    'is_available': is_available
                }
        
    except Exception as e:
        print(f"API fetch failed: {str(e)}")
    
    return None


def scrape_page(url, product_id=None):
    """Fallback: Scrape product data directly from page HTML"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Try window.__INITIAL_STATE__ (shoebox data) first as it's the most reliable for AE
        initial_state = extract_initial_state(soup, product_id)
        if initial_state:
            res = initial_state
        else:
            # Try JSON-LD second
            json_ld_data = extract_json_ld(soup)
            if json_ld_data:
                res = json_ld_data
            else:
                # Try __NEXT_DATA__ (Next.js sites)
                next_data = extract_next_data(soup)
                if next_data:
                    res = next_data
                else:
                    # Fallback to traditional CSS selector scraping
                    res = extract_from_html(soup)
        
        # FINAL CHECK: If any of the above said it's available, but the HTML text says it's not
        if res and res.get('is_available') is not False:
            if not check_html_unavailability(soup):
                res['is_available'] = False
                
        return res
    
    except Exception as e:
        print(f"Page scraping failed: {str(e)}")
        return None


def extract_json_ld(soup):
    """Extract product data from JSON-LD schema"""
    # Try multiple class names
    script_classes = ['qa-pdp-schema-org', 'schema-org', 'product-schema']
    
    for cls in script_classes:
        schema_script = soup.find('script', class_=cls)
        if schema_script and schema_script.string:
            try:
                data = json.loads(schema_script.string)
                return parse_json_ld(data)
            except json.JSONDecodeError:
                continue
    
    # Try finding by type attribute
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            result = parse_json_ld(data)
            if result and result.get('name'):
                return result
        except:
            continue
    
    return None


def parse_json_ld(data):
    """Parse JSON-LD product data"""
    # Handle array format
    if isinstance(data, list):
        for item in data:
            if item.get('@type') == 'Product':
                data = item
                break
        else:
            return None
    
    if data.get('@type') != 'Product':
        return None
    
    name = data.get('name')
    
    # Extract price from offers
    offers = data.get('offers', {})
    price = None
    
    if isinstance(offers, list) and len(offers) > 0:
        price = float(offers[0].get('price', 0))
    elif isinstance(offers, dict):
        price = float(offers.get('price', 0))
    
    # Get image
    image_url = data.get('image')
    if isinstance(image_url, list) and len(image_url) > 0:
        image_url = image_url[0]
    
    # Extract availability
    availability = offers.get('availability')
    is_available = True
    if availability == 'http://schema.org/OutOfStock' or availability == 'OutOfStock':
        is_available = False
    
    return {
        'name': name,
        'current_price': price,
        'list_price': price, # JSON-LD usually only has one price
        'image_url': image_url,
        'is_available': is_available
    }


def extract_next_data(soup):
    """Extract data from Next.js __NEXT_DATA__ script"""
    script = soup.find('script', id='__NEXT_DATA__')
    if script and script.string:
        try:
            data = json.loads(script.string)
            props = data.get('props', {}).get('pageProps', {})
            product = props.get('product') or props.get('productData')
            if product:
                current_price = product.get('salePrice') or product.get('price')
                list_price = product.get('listPrice') or current_price
                return {
                    'name': product.get('name') or product.get('productName'),
                    'current_price': float(current_price) if current_price else None,
                    'list_price': float(list_price) if list_price else None,
                    'image_url': product.get('image') or product.get('imageUrl'),
                    'is_available': product.get('isAvailable', True)
                }
        except:
            pass
    return None


def extract_initial_state(soup, product_id=None):
    """Extract data from window.__INITIAL_STATE__ or similar"""
    # Try shoebox script tags first (common in newer AE pages)
    shoebox_scripts = soup.find_all('script', id=lambda x: x and x.startswith('shoebox-'))
    for script in shoebox_scripts:
        if script.string:
            try:
                data = json.loads(script.string)
                
                # Collect all potential product/sku items
                candidates = []
                if 'data' in data:
                    if isinstance(data['data'], list):
                        candidates.extend(data['data'])
                    else:
                        candidates.append(data['data'])
                if 'included' in data:
                    candidates.extend(data['included'])
                
                best_name = None
                best_image = None
                current_price = None
                list_price = None
                sku_ids = []
                
                # 1. First pass: find all items that match the product_id or are linked to it
                for item in candidates:
                    attrs = item.get('attributes', {})
                    item_id = item.get('id')
                    repo_id = attrs.get('repositoryId')
                    
                    # If this is the main product, collect SKU IDs to look for prices later
                    if product_id and (product_id == item_id or product_id == repo_id):
                        if not best_name:
                            best_name = attrs.get('displayName') or attrs.get('name') or attrs.get('productName')
                        if not best_image:
                            best_image = (attrs.get('pdpImages') or [None])[0] or attrs.get('image')
                        
                        sku_refs = item.get('relationships', {}).get('skus', {}).get('data', [])
                        sku_ids.extend([s.get('id') for s in sku_refs if s.get('id')])

                # 2. Second pass: aggregate prices from main product AND all its SKUs
                for item in candidates:
                    attrs = item.get('attributes', {})
                    item_id = item.get('id')
                    repo_id = attrs.get('repositoryId')
                    
                    is_match = False
                    if product_id:
                        if item_id == product_id or repo_id == product_id or item_id in sku_ids:
                            is_match = True
                    else:
                        is_match = True # Take everything if no ID (fallback)
                        
                    if is_match:
                        s = attrs.get('salePrice') or attrs.get('sale_price')
                        l = attrs.get('listPrice') or attrs.get('list_price') or attrs.get('price')
                        
                        if l:
                            list_price = max(float(list_price) if list_price else 0, float(l))
                        if s:
                            current_price = float(s) if not current_price or float(s) < float(current_price) else current_price
                        
                        # Use list_price as current_price if s is missing
                        if not current_price and l:
                            current_price = float(l)
                
                if best_name and (current_price or list_price):
                    # Final sanity check: if list_price same as current_price, but we found a higher one elsewhere...
                    # (handled by max(l) logic above)
                    return {
                        'name': best_name,
                        'current_price': current_price or list_price,
                        'list_price': list_price or current_price,
                        'image_url': best_image,
                        'is_available': product.get('isAvailable', product.get('inStock', True))
                    }
            except:
                continue

    for script in soup.find_all('script'):
        if not script.string:
            continue
        
        # Look for various state patterns
        patterns = [
            r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
            r'window\.__PRELOADED_STATE__\s*=\s*({.+?});',
            r'"product"\s*:\s*({.+?})\s*[,}]',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, script.string, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                    if 'product' in data:
                        product = data['product']
                        current_price = product.get('salePrice') or product.get('price')
                        list_price = product.get('listPrice') or current_price
                        return {
                            'name': product.get('name'),
                            'current_price': float(current_price) if current_price else None,
                            'list_price': float(list_price) if list_price else None,
                            'image_url': product.get('image'),
                            'is_available': product.get('isAvailable', product.get('inStock', True))
                        }
                except:
                    continue
    
    return None


def extract_from_html(soup):
    """Extract product data from HTML elements"""
    # Product name selectors
    name = None
    name_selectors = [
        'h1.product-name',
        '.product-title',
        'h1[data-testid="product-name"]',
        '.product__title',
        'h1',
    ]
    
    for selector in name_selectors:
        elem = soup.select_one(selector)
        if elem and elem.text.strip():
            name = elem.text.strip()
            break
    
    # Price selectors
    price = None
    price_selectors = [
        '.product-price-text',
        '.product-price',
        '[data-testid="current-price"]',
        '.current-price',
        '.price',
        '.product__price',
    ]
    
    for selector in price_selectors:
        elems = soup.select(selector)
        for elem in elems:
            price_text = elem.text.strip()
            if '$' in price_text:
                # Extract numeric value
                price_match = re.search(r'\$(\d+\.?\d*)', price_text)
                if price_match:
                    price = float(price_match.group(1))
                    break
        if price:
            break
    
    # Image selectors
    image_url = None
    img_selectors = [
        '.product-image img',
        '.product__image img',
        'img[data-testid="product-image"]',
        '.gallery img',
    ]
    
    for selector in img_selectors:
        elem = soup.select_one(selector)
        if elem:
            image_url = elem.get('src') or elem.get('data-src')
            if image_url:
                break
    
    # Original price selectors
    list_price = None
    list_price_selectors = [
        '.product-list-price',
        '.old-price',
        '[data-testid="list-price"]',
        '.list-price',
    ]
    
    for selector in list_price_selectors:
        elem = soup.select_one(selector)
        if elem and '$' in elem.text:
            price_match = re.search(r'\$(\d+\.?\d*)', elem.text)
            if price_match:
                list_price = float(price_match.group(1))
                break
    
    if not list_price:
        list_price = price

    if name:
        return {
            'name': name,
            'current_price': price,
            'list_price': list_price,
            'image_url': image_url,
            'is_available': check_html_unavailability(soup)
        }
    
    return None

def check_html_unavailability(soup):
    """Utility to check if page text indicates out of stock status"""
    if soup.select('div[data-test-oos-label]') or soup.select('._oos-label_1bn8o3') or soup.select('.product-swatches-oos') or soup.select('._out-of-stock_1e4pqf'):
        return False

    return True
