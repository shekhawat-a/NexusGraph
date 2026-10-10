import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from app.api.upload_router import router as upload_router

# Import the OSINT router from the app directory
from app.api.osint_router import router as osint_router

# Securely load environment variables from .env file
load_dotenv()

# Initialize the FastAPI application
app = FastAPI(
    title="NexusGraph Backend",
    description="Financial Cybercrime Investigation Platform",
    version="1.0.0"
)

# Configure CORSMiddleware for local Next.js / React frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for development
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
)

# Root endpoint added to fix the 404 Not Found error
@app.get("/", status_code=200)
async def read_root():
    """
    Root endpoint to prevent 404 errors on the base URL.
    """
    return {"message": "Welcome to NexusGraph API! Navigate to /docs to test your TinyFish endpoints."}

@app.get("/health", status_code=200)
async def health_check():
    """
    Basic health check endpoint to verify API uptime.
    """
    return {"status": "ok", "message": "NexusGraph Backend is operational."}

# Mount the OSINT router with the specified prefix and tags
app.include_router(
    upload_router,
    prefix="/api/upload",
    tags=["Data Ingestion & Staging"]
)

if __name__ == "__main__":
    import uvicorn
    # Run the server with uvicorn if executed directly
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)