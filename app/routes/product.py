from fastapi import APIRouter, UploadFile, File
from fastapi.responses import JSONResponse
from app.services.gemini import analyze_images, find_shopping_links
from app.services.firecrawl import call_firecrawl_extractor
from app.utils.image_tools import encode_image_to_base64
from PIL import Image
import io
import base64

router = APIRouter()

@router.post("/analyze")
async def analyze_product(images: list[UploadFile] = File(...)):
    img_base64_list = []
    for image in images:
        img_bytes = await image.read()
        img_base64 = base64.b64encode(img_bytes).decode("utf-8")
        img_base64_list.append(img_base64)
    product_desc = analyze_images(img_base64_list)
    shopping_links = find_shopping_links(product_desc)
    firecrawl_result = call_firecrawl_extractor(shopping_links)
    return {
        "product_description": product_desc,
        "shopping_links": shopping_links,
        "firecrawl_result": firecrawl_result
    }

