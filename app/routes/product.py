from fastapi import APIRouter, UploadFile, File, Form
from typing import List
from app.services.gemini import analyze_images, find_shopping_links
from app.services.firecrawl import call_firecrawl_extractor
import base64
import uuid
import time

router = APIRouter()

@router.post("/analyze/image")
async def analyze_product_images(images: List[UploadFile] = File(...)):
    request_id = str(uuid.uuid4())[:8]  # Short unique ID for logging
    img_base64_list = []
    for image in images:
        img_bytes = await image.read()
        img_base64 = base64.b64encode(img_bytes).decode("utf-8")
        img_base64_list.append(img_base64)
    product_desc = analyze_images(img_base64_list)
    shopping_links = find_shopping_links(product_desc)
    start_time = time.time()
    print(f"[Firecrawl] Request {request_id} started.")
    firecrawl_output = await call_firecrawl_extractor(shopping_links, request_id)
    elapsed = time.time() - start_time
    print(f"[Firecrawl] Request {request_id} completed in {elapsed:.2f} seconds")
    return firecrawl_output

@router.post("/analyze/search")
async def analyze_product_search(search_terms: List[str] = Form(...)):
    request_id = str(uuid.uuid4())[:8]
    product_desc = " ".join(search_terms)
    shopping_links = find_shopping_links(product_desc)
    start_time = time.time()
    print(f"[Firecrawl] Request {request_id} started.")
    firecrawl_output = await call_firecrawl_extractor(shopping_links, request_id)
    elapsed = time.time() - start_time
    print(f"[Firecrawl] Request {request_id} completed in {elapsed:.2f} seconds")
    return firecrawl_output
