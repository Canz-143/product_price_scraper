from fastapi import APIRouter, UploadFile, File
from fastapi.responses import JSONResponse
from app.services.gemini import analyze_image, find_shopping_links
from app.services.firecrawl import call_firecrawl_extractor
from app.utils.image_tools import encode_image_to_base64
from PIL import Image
import io

router = APIRouter()

@router.post("/analyze")
async def analyze_product(image_file: UploadFile = File(...)):
    image_data = await image_file.read()
    image = Image.open(io.BytesIO(image_data))

    img_base64 = encode_image_to_base64(image)
    product_desc = analyze_image(img_base64)
    shopping_links = find_shopping_links(product_desc)
    firecrawl_result = call_firecrawl_extractor(shopping_links)

    return JSONResponse({
        "product_description": product_desc,
        "shopping_links": shopping_links,
        "firecrawl_result": firecrawl_result
    })

