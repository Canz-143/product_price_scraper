import asyncio
import httpx
import json
from app.config import FIRECRAWL_API_KEY

firecrawl_semaphore = asyncio.Semaphore(2)  # Only 1 concurrent Firecrawl request allowed

async def call_firecrawl_extractor(links, request_id=None):
    async with firecrawl_semaphore:
        # Only send the first 10 links
        limited_links = links[:3]
        # Resolve each link asynchronously (sequentially)
        resolved_links = []
        for link in limited_links:
            resolved = await resolve_vertex_url(link)
            # Only include successfully resolved URLs (skip if error or unresolved)
            if resolved and resolved != link:
                resolved_links.append(resolved)
            else:
                print(f"[Firecrawl] Skipping unresolved Vertex URL: {link}")
        #print(f"[Firecrawl] Resolved URLs: {resolved_links}")

        url = "https://api.firecrawl.dev/v1/extract"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {FIRECRAWL_API_KEY}"
        }
        payload = {
            "urls": resolved_links,
            "prompt": (
                "Extract the price and product URL from the specified product page. "
                "Only get the main price even if the product is out of stock, and the direct product page URL; one set per URL. "
                "Include website name. If it's a search result page, skip it, don't scrape anything."
            ),
            "scrapeOptions": {
                "maxAge": 604800000
            },
            "schema": {
                "type": "object",
                "properties": {
                    "ecommerce_links": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "website_name": {"type": "string"},
                                "price": {"type": "string"},
                                "website_url": {"type": "string"}
                            },
                            "required": ["website_name", "price", "website_url"]
                        }
                    }
                },
                "required": ["ecommerce_links"]
            }
        }

        # Log the POST request payload and URL
        #print(f"[Firecrawl] POST URL: {url}")
        #print(f"[Firecrawl] POST Payload: {json.dumps(payload, indent=2)}")
        #print(f"[Firecrawl] POST Headers: {headers}")

        # Set a longer timeout for the HTTPX client
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            try:
                firecrawl_result = response.json()
            except Exception as e:
                print(f"[Firecrawl] Error decoding JSON: {e}")
                print(f"[Firecrawl] Raw response: {response.text}")
                return {"success": False, "error": "Invalid JSON from Firecrawl"}

            firecrawl_output = None
            if firecrawl_result.get("success") and firecrawl_result.get("id"):
                firecrawl_id = firecrawl_result["id"]
                print(f"[Firecrawl] Waiting 20 seconds before fetching result for id: {firecrawl_id}")
                await asyncio.sleep(5)
                get_url = f"https://api.firecrawl.dev/v1/extract/{firecrawl_id}"
                while True:
                    get_response = await client.get(get_url, headers=headers)
                    try:
                        firecrawl_output = get_response.json()
                    except Exception as e:
                        print(f"[Firecrawl] Error decoding JSON: {e}")
                        print(f"[Firecrawl] Raw response: {get_response.text}")
                        firecrawl_output = {"success": False, "error": "Invalid JSON from Firecrawl"}
                        break
                    status = firecrawl_output.get("status") or firecrawl_output.get("data", {}).get("status")
                    print(f"[Firecrawl] Request {request_id} status: {status}")
                    if status == "completed":
                        break
                    elif status == "processing":
                        print(f"[Firecrawl] Request {request_id} still processing...")
                        await asyncio.sleep(1)
                    else:
                        break

        # ✅ Only return the relevant clean portion
        if firecrawl_output and firecrawl_output.get("success"):
            return firecrawl_output
    return None

async def resolve_vertex_url(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    async with httpx.AsyncClient(follow_redirects=False, timeout=10.0) as client:
        try:
            resp = await client.head(url, headers=headers)
            location = resp.headers.get("Location")
            # Optionally follow one more redirect
            if resp.is_redirect and location:
                resp2 = await client.head(location, headers=headers)
                next_location = resp2.headers.get("Location")
                return next_location or location
            return location or url
        except Exception as e:
            print(f"[Vertex Redirect] Error resolving {url}: {e}")
            return url
