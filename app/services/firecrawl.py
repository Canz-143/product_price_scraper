import asyncio
import httpx
import json
import re
from urllib.parse import urlparse, parse_qs
from app.config import FIRECRAWL_API_KEY

firecrawl_semaphore = asyncio.Semaphore(10)  # Limit concurrent Firecrawl requests

def is_valid_url(url):
    """
    Check if URL is valid and has proper format for Firecrawl
    Returns True if valid, False if should be filtered out
    """
    if not url:
        return False
    
    # Must start with http:// or https://
    if not url.startswith(('http://', 'https://')):
        return False
    
    try:
        parsed = urlparse(url)
        # Must have a valid domain
        if not parsed.netloc:
            return False
        # Must have a proper TLD (at least one dot in domain)
        if '.' not in parsed.netloc:
            return False
        # Filter out blocked/tracking URLs
        if '/blocked?' in url or 'blocked' in parsed.path:
            return False
        return True
    except Exception:
        return False

def is_search_or_collection_page(url):
    """
    Determine if a URL is a search result page or collection page
    Returns True if it should be filtered out, False if it's a product page
    """
    if not url:
        return True
    
    parsed_url = urlparse(url.lower())
    path = parsed_url.path
    query_params = parse_qs(parsed_url.query)
    
    # Search page indicators
    search_indicators = [
        # URL path patterns
        r'/search',
        r'/results',
        r'/find',
        r'/query',
        r'/s/',
        r'/buscar',  # Spanish
        r'/recherche',  # French
        r'/suche',  # German
    ]
    
    # Collection/category page indicators
    collection_indicators = [
        r'/category',
        r'/categories',
        r'/collection',
        r'/collections',
        r'/browse',
        r'/catalog',
        r'/products(?:/(?:all|list))?$',  # /products, /products/all, /products/list
        r'/items',
        r'/list',
        r'/archive',
        r'/tag/',
        r'/tags/',
        r'/c/',
        r'/cat/',
        r'/department',
        r'/shop(?:/(?:all|category))?$',  # /shop, /shop/all, /shop/category
    ]
    
    # Check URL path for search patterns
    for pattern in search_indicators:
        if re.search(pattern, path):
            return True
    
    # Check URL path for collection patterns
    for pattern in collection_indicators:
        if re.search(pattern, path):
            return True
    
    # Check query parameters for search indicators
    search_params = ['q', 'query', 'search', 'keyword', 'term', 'find', 's', 'k', 'p']
    for param in search_params:
        if param in query_params:
            return True
    
    # Check query parameters for collection/filtering indicators
    collection_params = ['category', 'cat', 'collection', 'tag', 'filter', 'sort']
    collection_param_count = sum(1 for param in collection_params if param in query_params)
    
    # If multiple collection parameters are present, it's likely a collection page
    if collection_param_count >= 2:
        return True
    
    # Check for pagination parameters combined with other indicators
    pagination_params = ['page', 'p', 'offset', 'start', 'limit']
    has_pagination = any(param in query_params for param in pagination_params)
    
    if has_pagination and collection_param_count >= 1:
        return True
    
    # Domain-specific patterns
    domain = parsed_url.netloc
    
    # Amazon-specific patterns
    if 'amazon.' in domain:
        # Amazon search results
        if '/s?' in url or '/s/' in path:
            return True
        # Amazon category pages
        if re.search(r'/b/|/gp/browse/|/departments/', path):
            return True
    
    # eBay-specific patterns
    elif 'ebay.' in domain:
        if '/sch/' in path or '/b/' in path:
            return True
    
    # Shopify stores
    elif 'shopify' in domain or '/collections/' in path:
        if '/collections/' in path and not re.search(r'/collections/[^/]+/products/', path):
            return True
    
    # Etsy-specific patterns
    elif 'etsy.' in domain:
        if '/search/' in path or '/c/' in path:
            return True
    
    # Walmart-specific patterns
    elif 'walmart.' in domain:
        if '/search/' in path or '/browse/' in path:
            return True
    
    # Target-specific patterns
    elif 'target.' in domain:
        if '/s/' in path or '/c/' in path:
            return True
    
    return False

def is_likely_product_page(url):
    """
    Additional check to identify likely product pages
    Returns True if it looks like a product page
    """
    if not url:
        return False
    
    parsed_url = urlparse(url.lower())
    path = parsed_url.path
    
    # Product page indicators
    product_indicators = [
        r'/product/',
        r'/item/',
        r'/p/',
        r'/dp/',  # Amazon
        r'/itm/',  # eBay
        r'/listing/',  # Etsy
        r'/products/[^/]+$',  # Shopify pattern
        r'/[^/]+-p-\d+',  # Common product ID patterns
        r'/\d+\.html?$',  # Numeric product IDs
    ]
    
    for pattern in product_indicators:
        if re.search(pattern, path):
            return True
    
    # Check if path ends with what looks like a product identifier
    path_parts = [part for part in path.split('/') if part]
    if path_parts:
        last_part = path_parts[-1]
        # Product pages often end with product names or IDs
        if re.search(r'^[a-zA-Z0-9\-_]+$', last_part) and len(last_part) > 3:
            return True
    
    return False

async def call_firecrawl_extractor(links, request_id=None):
    async with firecrawl_semaphore:
        # Limit to the first 10 links
        limited_links = links[:5]

        # Resolve all links concurrently (parallel)
        resolved_links_raw = await asyncio.gather(*(resolve_vertex_url(link) for link in limited_links))
        
        # Filter out unresolved links, duplicates, and search/collection pages
        resolved_links = []
        filtered_count = 0
        
        for original, resolved in zip(limited_links, resolved_links_raw):
            if not resolved or resolved == original:
                print(f"[Firecrawl] Skipping unresolved Vertex URL: {original}")
                continue
            
            # First check: Valid URL format
            if not is_valid_url(resolved):
                filtered_count += 1
                print(f"[Firecrawl] Filtered out invalid URL: {resolved}")
                continue
            
            # Check if it's a search or collection page
            if is_search_or_collection_page(resolved):
                filtered_count += 1
                print(f"[Firecrawl] Filtered out search/collection page: {resolved}")
                continue
            
            # Additional check for product pages (optional, more permissive)
            if not is_likely_product_page(resolved):
                # Only filter if we're confident it's not a product page
                # This is more lenient to avoid false positives
                parsed = urlparse(resolved.lower())
                if any(indicator in parsed.path for indicator in ['/search', '/category', '/collection', '/browse']):
                    filtered_count += 1
                    print(f"[Firecrawl] Filtered out non-product page: {resolved}")
                    continue
            
            resolved_links.append(resolved)
        
        print(f"[Firecrawl] Filtered out {filtered_count} search/collection pages")
        print(f"[Firecrawl] Final resolved URLs: {resolved_links}")

        # If no valid product URLs remain, return early
        if not resolved_links:
            print("[Firecrawl] No valid product URLs after filtering")
            return {"success": False, "error": "No valid product URLs after filtering search/collection pages"}

        url = "https://api.firecrawl.dev/v1/extract"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {FIRECRAWL_API_KEY}"
        }
        payload = {
            "urls": resolved_links,
            "prompt": (
                "Extract the product price as a combined string (e.g., $2000), the price as a string (e.g., 2000), the currency code (e.g., USD), and include the website name and the direct product page URL."
            ),
            "schema": {
                "type": "object",
                "properties": {
                    "ecommerce_links": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "website_name": {"type": "string"},
                                "price_combined": {"type": "string"},
                                "price_string": {"type": "string"},
                                "currency_code": {"type": "string"},
                                "website_url": {"type": "string"}
                            },
                            "required": ["website_name", "price_combined", "price_string", "currency_code", "website_url"]
                        }
                    }
                },
                "required": ["ecommerce_links"]
            }
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            try:
                firecrawl_result = response.json()
            except Exception as e:
                print(f"[Firecrawl] Error decoding JSON: {e}")
                print(f"[Firecrawl] Raw response: {response.text}")
                return {"success": False, "error": "Invalid JSON from Firecrawl"}

            # Handle both sync and async responses
            if firecrawl_result.get("success"):
                
                # Check if it's an async response (has job ID)
                if firecrawl_result.get("id"):
                    print(f"[Firecrawl] Got async response, polling for job ID: {firecrawl_result['id']}")
                    firecrawl_id = firecrawl_result["id"]
                    #print(f"[Firecrawl] Waiting 5 seconds before fetching result for id: {firecrawl_id}")
                    await asyncio.sleep(5)
                    
                    get_url = f"https://api.firecrawl.dev/v1/extract/{firecrawl_id}"
                    while True:
                        get_response = await client.get(get_url, headers=headers)
                        try:
                            firecrawl_output = get_response.json()
                        except Exception as e:
                            print(f"[Firecrawl] Error decoding JSON: {e}")
                            print(f"[Firecrawl] Raw response: {get_response.text}")
                            return {"success": False, "error": "Invalid JSON from Firecrawl"}
                        
                        status = firecrawl_output.get("status") or firecrawl_output.get("data", {}).get("status")
                        #print(f"[Firecrawl] Request {request_id} status: {status}")
                        if status == "completed":
                            break
                        elif status == "processing":
                            #print(f"[Firecrawl] Request {request_id} still processing...")
                            await asyncio.sleep(3)
                        else:
                            break
                    
                    return firecrawl_output
                
                # Check if it's a sync response (has data directly)
                elif firecrawl_result.get("data") or firecrawl_result.get("status") == "completed":
                    #print(f"[Firecrawl] Got synchronous response - data ready immediately")
                    return firecrawl_result
                
                else:
                    print(f"[Firecrawl] Unexpected success response structure: {firecrawl_result}")
                    return {"success": False, "error": "Unexpected response structure from Firecrawl"}
            
            else:
                print(f"[Firecrawl] API returned failure: {firecrawl_result}")
                return firecrawl_result

    return {"success": False, "error": "Unknown error in Firecrawl extraction"}

async def resolve_vertex_url(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    async with httpx.AsyncClient(follow_redirects=False, timeout=10.0) as client:
        try:
            resp = await client.head(url, headers=headers)
            location = resp.headers.get("Location")
            if resp.is_redirect and location:
                resp2 = await client.head(location, headers=headers)
                next_location = resp2.headers.get("Location")
                return next_location or location
            return location or url
        except Exception as e:
            #print(f"[Vertex Redirect] Error resolving {url}: {e}")
            return url
