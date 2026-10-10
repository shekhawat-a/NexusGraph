import os
import json
from typing import Literal, List, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, status
from dotenv import load_dotenv

# 1. IMPORT THE OFFICIAL TINYFISH SDK
from tinyfish import TinyFish

# Load the .env file
load_dotenv() 

# Initialize the API Router
router = APIRouter()

# ---------------------------------------------------------
# Pydantic Schemas for Request & Response Validation
# ---------------------------------------------------------

class OSINTRequest(BaseModel):
    query: str = Field(
        ..., 
        description="The target entity identifier (e.g., phone number or company name)."
    )
    target_type: Literal["phone", "shell_company"] = Field(
        ..., 
        description="The type of OSINT investigation to perform."
    )

class OSINTResponse(BaseModel):
    status: str = Field(..., description="Status of the investigation (e.g., 'success').")
    extracted_nodes: List[Dict[str, Any]] = Field(
        ..., 
        description="List of resolved entities and connections discovered by TinyFish."
    )
    raw_agent_log: str = Field(
        ..., 
        description="The raw execution log/reasoning trace from the TinyFish web agent."
    )

# ---------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------

@router.post("/scan", response_model=OSINTResponse)
def scan_target(request: OSINTRequest):
    """
    Initiates a TinyFish web agent scan using the official Python SDK.
    """
    # 1. Verify the key exists (TinyFish SDK reads this automatically, 
    # but we check here to give a clear error if you forgot it).
    if not os.getenv("TINYFISH_API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="TINYFISH_API_KEY is not configured in the .env file."
        )

    # 2. Initialize the official TinyFish Client
    try:
        client = TinyFish()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize TinyFish client: {str(e)}"
        )

    # 3. Setup the OSINT Web Agent Command
    # We point the agent to Google to start its search based on your query
    search_query = request.query.replace(" ", "+")
    starting_url = f"https://www.google.com/search?q={search_query}"
    
    # Instruct the agent to strictly return JSON so we can map it to our graph nodes
    agent_goal = (
        f"Conduct an OSINT investigation on the {request.target_type}: '{request.query}'. "
        f"Identify all associated entities (people, other companies, phone numbers). "
        f"You MUST return the final result strictly as a JSON object containing a 'nodes' array. "
        f"Example: {{\"nodes\": [{{\"id\": \"Name\", \"type\": \"Person\"}}]}}"
    )

    # 4. Execute the Agent using official syntax
    try:
        # Note: According to the docs, this is a synchronous call
        result = client.agent.run(
            url=starting_url,
            goal=agent_goal
        )
        
        # Convert the result to string to parse it
        result_text = str(result)
        extracted_nodes = []
        
        # Attempt to parse the JSON returned by the agent
        try:
            start_idx = result_text.find('{')
            end_idx = result_text.rfind('}')
            if start_idx != -1 and end_idx != -1:
                json_str = result_text[start_idx:end_idx+1]
                parsed_json = json.loads(json_str)
                extracted_nodes = parsed_json.get("nodes", [])
        except Exception:
            # If the agent didn't return perfect JSON, we fallback to an empty list 
            # but still provide the raw text in the log.
            pass

        return OSINTResponse(
            status="success",
            extracted_nodes=extracted_nodes,
            raw_agent_log=result_text
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"The TinyFish web agent encountered an error: {str(e)}"
        )