import os
import re
from google import genai
from google.genai.types import Tool, GoogleSearch
from google.genai.types import GenerateContentConfig
from app.config import GOOGLE_API_KEY

client = genai.Client()
model_id = "gemini-2.5-flash"
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

def analyze_images(img_base64_list):
    prompt = (
        "Identify this product with maximum specific detail. "
        "Provide brand, make, model, full product name, and key technical specifications. "
        "At the end, clearly list typical search terms, inside double quotes if possible, "
        "or as bullet points if that's clearer."
    )
    contents = [{
        "parts": [
            {"text": prompt},
            *[
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": img_base64
                    }
                }
                for img_base64 in img_base64_list
            ]
        ]
    }]
    response = client.models.generate_content(
        model=model_id,
        contents=contents,
        config=config
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
    # Limit to top 3 search terms
    search_terms = search_terms[:3]

    all_links = set()
    for term in search_terms:
        prompt = f"""
Find direct product purchase pages for: {term}
Use Google Search to locate specific product pages where customers can directly buy this exact item. Include only direct product pages with purchase options, official retailer/manufacturer pages, and e-commerce sites selling the specific product. Exclude product manuals or documentation, search results or category pages, review sites without purchase links, and out-of-stock listings. Provide clean URLs only, one per line.

Output format: URL
"""
        response = client.models.generate_content(
            model=model_id,
            contents=prompt,
            config=config
        )
        candidate = response.candidates[0]
        if (
            hasattr(candidate, "grounding_metadata")
            and candidate.grounding_metadata
            and hasattr(candidate.grounding_metadata, "grounding_chunks")
            and candidate.grounding_metadata.grounding_chunks
        ):
            for chunk in candidate.grounding_metadata.grounding_chunks:
                if hasattr(chunk, "web"):
                    all_links.add(chunk.web.uri)
    return list(all_links)

def extract_shopping_links_urls(response):
    """
    Extracts only the URLs (for Firecrawl) from the Gemini response.
    """
    links = []
    # Try grounding metadata
    if hasattr(response.candidates[0], 'grounding_metadata') and response.candidates[0].grounding_metadata:
        for chunk in response.candidates[0].grounding_metadata.grounding_chunks:
            if hasattr(chunk, 'web'):
                links.append(chunk.web.uri)
    # Fallback
    if not links:
        fallback_links = re.findall(r'\[(.*?)\]\((https?://[^\)]+)\)', response.text)
        links.extend([url for _, url in fallback_links])
    return links
