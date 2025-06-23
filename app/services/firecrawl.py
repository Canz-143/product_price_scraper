import requests
import json
from app.config import FIRECRAWL_API_KEY

def call_firecrawl_extractor(links):
    print(f"[Firecrawl] Sending URLs: {links}")  # Log the URLs being sent
    url = "https://api.firecrawl.dev/v1/extract"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}"
    }
    payload = {
        "urls": links,
        "prompt": "Extract the price from the specified product page. Only get the main price; one price per URL. Include product name if available.",
        "schema": {
            "type": "object",
            "properties": {
                "products": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_name": {"type": "string"},
                            "price": {"type": "string"}
                        },
                        "required": ["product_name", "price"]
                    }
                }
            },
            "required": ["products"]
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    return response.json()
