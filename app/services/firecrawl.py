import asyncio
import httpx
import json
from app.config import FIRECRAWL_API_KEY

async def call_firecrawl_extractor(links):
    # Only send the first 10 links
    limited_links = links[:6]
    print(f"[Firecrawl] Sending URLs (max 10): {limited_links}")  # Log the URLs being sent
    url = "https://api.firecrawl.dev/v1/extract"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}"
    }
    payload = {
        "urls": limited_links,
        "prompt": (
            "Extract the price and product URL from the specified product page. "
            "Only get the main price even if the product is out of stock, and the direct product page URL; one set per URL. "
            "Include website name."
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

    async with httpx.AsyncClient() as client:
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
                print(f"[Firecrawl] Status: {status}")
                if status == "completed":
                    break
                elif status == "processing":
                    print("[Firecrawl] Still processing, waiting 5 seconds...")
                    await asyncio.sleep(3)
                else:
                    break

    # ✅ Only return the relevant clean portion
    if firecrawl_output and firecrawl_output.get("success"):
        return firecrawl_output
    return None
