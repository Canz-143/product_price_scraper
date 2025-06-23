import os
import re
from google import genai
from google.genai.types import Tool, GoogleSearch
from google.genai.types import GenerateContentConfig
from app.config import GOOGLE_API_KEY

client = genai.Client()
model_id = "gemini-2.5-flash-preview-05-20"
search_tool = Tool(google_search=GoogleSearch())

config = GenerateContentConfig(
    system_instruction=(
        "You are a product identification assistant that can recognize products in images "
        "and provide detailed information about them. Focus on identifying the exact brand, "
        "make, model, and key specs, so users can find and buy this specific item online. "
        "At the end, always clearly list typical search terms either quoted or bullet-listed."
    ),
    tools=[search_tool],
    response_modalities=["TEXT"],
    temperature=0.2,
)

def analyze_image(img_base64: str):
    prompt = (
        "Identify this product with maximum specific detail. "
        "Provide brand, make, model, full product name, and key technical specifications. "
        "At the end, clearly list typical search terms, inside double quotes if possible, "
        "or as bullet points if that's clearer."
    )
    response = client.models.generate_content(
        model=model_id,
        contents=[
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": img_base64
                        }
                    }
                ]
            }
        ]
    )
    return response.text

def extract_search_terms(product_description):
    match = re.search(r'(search terms.*?)[:：]\s*(.*?)$', product_description, re.IGNORECASE | re.DOTALL)
    if not match:
        return []
    block = match.group(2).strip()
    terms = re.findall(r'"(.*?)"', block)
    if terms:
        return terms
    lines = [line.strip('-*• ').strip() for line in block.splitlines() if line.strip()]
    return lines

def find_shopping_links(product_description: str):
    search_terms = extract_search_terms(product_description)
    if not search_terms:
        search_terms = [product_description]

    improved_prompt = f"""
Use ONLY these exact search terms to find direct product pages:
{chr(10).join(['- ' + term for term in search_terms])}

❌ Do NOT include:
- Reviews, blogs, forums, social media
- Comparison or aggregator sites without a direct “Buy Now”
- Retailer homepages or generic categories
- Search result pages

✅ Only provide direct product pages with an “Add to Cart” or “Buy Now”.

Output format: [Product Title](URL)

If you can't find direct product pages, return “No direct product pages found.”
"""

    response = client.models.generate_content(
        model=model_id,
        contents=improved_prompt,
        config=config
    )

    links = []
    candidate = response.candidates[0]
    if (
        hasattr(candidate, "grounding_metadata")
        and candidate.grounding_metadata
        and hasattr(candidate.grounding_metadata, "grounding_chunks")
        and candidate.grounding_metadata.grounding_chunks
    ):
        for chunk in candidate.grounding_metadata.grounding_chunks:
            if hasattr(chunk, "web"):
                links.append(chunk.web.uri)
    return links
