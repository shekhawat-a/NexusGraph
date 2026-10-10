import json
import os
from typing import Any, Dict, List, Literal

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

load_dotenv()

try:
    from tinyfish import TinyFish
except ImportError:  # pragma: no cover - optional dependency
    TinyFish = None

router = APIRouter()


class OSINTRequest(BaseModel):
    query: str = Field(..., description="The target entity identifier (e.g., phone number or company name).")
    target_type: Literal["phone", "shell_company"] = Field(..., description="The type of OSINT investigation to perform.")


class OSINTResponse(BaseModel):
    status: str = Field(..., description="Status of the investigation (e.g., 'success').")
    extracted_nodes: List[Dict[str, Any]] = Field(..., description="List of resolved entities and connections discovered by TinyFish.")
    raw_agent_log: str = Field(..., description="The raw execution log/reasoning trace from the TinyFish web agent.")


@router.post("/scan", response_model=OSINTResponse)
def scan_target(request: OSINTRequest):
    """Run an OSINT scan when the TinyFish SDK and API key are available."""
    if TinyFish is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TinyFish SDK is not installed. Install the backend requirements to enable OSINT scans.",
        )

    if not os.getenv("TINYFISH_API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="TINYFISH_API_KEY is not configured in the .env file.",
        )

    try:
        client = TinyFish()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize TinyFish client: {exc}",
        ) from exc

    search_query = request.query.replace(" ", "+")
    starting_url = f"https://www.google.com/search?q={search_query}"
    agent_goal = (
        f"Conduct an OSINT investigation on the {request.target_type}: '{request.query}'. "
        f"Identify all associated entities (people, other companies, phone numbers). "
        f"Return a final JSON object containing a 'nodes' array. "
        f"Example: {{\"nodes\": [{{\"id\": \"Name\", \"type\": \"Person\"}}]}}"
    )

    try:
        result = client.agent.run(url=starting_url, goal=agent_goal)
        result_text = str(result)
        extracted_nodes = []

        try:
            start_idx = result_text.find("{")
            end_idx = result_text.rfind("}")
            if start_idx != -1 and end_idx != -1:
                json_str = result_text[start_idx : end_idx + 1]
                parsed_json = json.loads(json_str)
                extracted_nodes = parsed_json.get("nodes", [])
        except Exception:
            pass

        return OSINTResponse(status="success", extracted_nodes=extracted_nodes, raw_agent_log=result_text)

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"The TinyFish web agent encountered an error: {exc}",
        ) from exc