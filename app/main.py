from fastapi import FastAPI
from app.routes import product

app = FastAPI()

# Include product routes
app.include_router(product.router)
