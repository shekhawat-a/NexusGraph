import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# 1. IMPORT ALL ROUTERS
from app.api.osint_router import router as osint_router
from app.api.upload_router import router as upload_router
from app.api.graph_router import router as graph_router

# 2. LOAD ENVIRONMENT VARIABLES
load_dotenv()

# 3. INITIALIZE FASTAPI APP
app = FastAPI(
    title="NexusGraph Backend",
    description="Financial Cybercrime Investigation Platform (Hackathon Edition)",
    version="1.0.0"
)

# 4. CONFIGURE CORS (Crucial for Shivang's Frontend to connect without errors)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins during local development
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)

# 5. SYSTEM ENDPOINTS
@app.get("/", status_code=200, tags=["System"])
async def read_root():
    """Root endpoint to prevent 404 errors on the base URL."""
    return {"message": "Welcome to NexusGraph API! Navigate to /docs to test all endpoints."}

@app.get("/health", status_code=200, tags=["System"])
async def health_check():
    """Basic health check endpoint to verify API uptime."""
    return {"status": "ok", "message": "NexusGraph Backend is fully operational."}

# 6. MOUNT THE ROUTERS (The core engine of your backend)
app.include_router(
    osint_router,
    prefix="/api/osint",
    tags=["TinyFish OSINT"]
)

app.include_router(
    upload_router,
    prefix="/api/upload",
    tags=["Data Ingestion & AI Extraction"]
)

# Tajpreet's graph router already has prefix="/api/graph" defined inside it, so we just include it
app.include_router(
    graph_router
)

# 7. RUN SERVER
if __name__ == "__main__":
    import uvicorn
    # Run the server with uvicorn if executed directly
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)