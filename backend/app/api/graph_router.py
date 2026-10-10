"""
graph_router.py
===============
Quantum Veil - Financial Cybercrime Investigation Platform
FastAPI router exposing the investigation graph analytics.

Endpoints (all under /api/graph)
--------------------------------
GET /              Full network graph for the frontend  -> {"nodes": [...], "edges": [...]}
GET /freeze-list   Priority-sorted bank accounts to freeze
GET /mules         Detected money-mule accounts
GET /suspects      Ranked Person/Company suspects (masterminds)

Wiring it up (in app/main.py):
    from fastapi import FastAPI
    from app.routers.graph_router import router as graph_router

    app = FastAPI(title="Quantum Veil")
    app.include_router(graph_router)

Demo mode:
    The router seeds itself with mock data on first use, so every endpoint
    returns valid JSON immediately - no database or upload step required.
    Swap `_load_demo_sources()` for real data loaders in production.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional

import networkx as nx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.services.graph_engine import (
    build_investigation_graph,
    detect_mules,
    export_graph_for_ui,
    generate_freeze_list,
    rank_suspects,
)

logger = logging.getLogger("quantum_veil.graph_router")

# --------------------------------------------------------------------------- #
# 1. Router setup
# --------------------------------------------------------------------------- #

router = APIRouter(
    prefix="/api/graph",
    tags=["Investigation Graph"],
    responses={500: {"description": "Graph engine failure"}},
)


# --------------------------------------------------------------------------- #
# Response models (extra fields allowed so engine output can evolve freely)
# --------------------------------------------------------------------------- #

class GraphNode(BaseModel):
    """A node in the UI graph (Person / Phone / BankAccount / Company)."""
    model_config = ConfigDict(extra="allow")
    id: str
    type: str
    source: str = ""
    label: str = ""


class GraphEdge(BaseModel):
    """A directed edge in the UI graph (CALLED / TRANSFERRED / DIRECTOR_OF ...)."""
    model_config = ConfigDict(extra="allow")
    source: str
    target: str
    relation: str


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class FreezeEntry(BaseModel):
    model_config = ConfigDict(extra="allow")
    priority: int
    account_id: str
    throughput: float
    priority_score: float
    is_mule: bool
    owner: Optional[str] = None


class MuleEntry(BaseModel):
    model_config = ConfigDict(extra="allow")
    account_id: str
    in_degree: int
    out_degree: int
    mule_score: float


class SuspectEntry(BaseModel):
    model_config = ConfigDict(extra="allow")
    rank: int
    id: str
    type: str
    name: str
    suspect_score: float


# --------------------------------------------------------------------------- #
# 4. Mock data for the hackathon demo
# --------------------------------------------------------------------------- #

def _load_demo_sources() -> tuple[dict, dict, list]:
    """
    Return (offline_data, osint_data, bank_logs) mock datasets.

    Scenario: three victims pay a shell-company account (ACC_3003), which
    immediately fans the money out to three accounts that consolidate into a
    second shell (ACC_4004) and then move offshore.
    """
    offline_data = {
        "persons": [
            {"id": "P_RAVI", "name": "Ravi Kumar"},
            {"id": "P_NEHA", "name": "Neha Singh"},
            {"id": "P_ARJUN", "name": "Arjun Mehta"},
            {"id": "P_SARA", "name": "Sara Khan"},
        ],
        "phones": [
            {"id": "PH_9811", "owner": "P_RAVI"},
            {"id": "PH_9822", "owner": "P_NEHA"},
            {"id": "PH_9833", "owner": "P_ARJUN"},
            {"id": "PH_9844", "owner": "P_SARA"},
        ],
        "companies": [
            {"id": "C_SHELL1", "name": "Nova Trade Pvt Ltd"},
            {"id": "C_SHELL2", "name": "BlueSky Exports LLP"},
        ],
        "bank_accounts": [
            {"id": "ACC_1001", "owner": "P_RAVI"},
            {"id": "ACC_2002", "owner": "P_NEHA"},
            {"id": "ACC_3003", "owner": "C_SHELL1"},
            {"id": "ACC_4004", "owner": "C_SHELL2"},
        ],
        "call_records": [
            {"caller": "PH_9811", "callee": "PH_9822", "duration_sec": 320, "timestamp": "2026-09-01T10:00:00"},
            {"caller": "PH_9811", "callee": "PH_9822", "duration_sec": 150, "timestamp": "2026-09-02T11:30:00"},
            {"caller": "PH_9822", "callee": "PH_9833", "duration_sec": 90, "timestamp": "2026-09-02T12:00:00"},
            {"caller": "PH_9833", "callee": "PH_9844", "duration_sec": 45, "timestamp": "2026-09-03T09:15:00"},
        ],
        "directorships": [
            {"person": "P_ARJUN", "company": "C_SHELL1"},
            {"person": "P_NEHA", "company": "C_SHELL1"},
            {"person": "P_ARJUN", "company": "C_SHELL2"},
        ],
    }

    osint_data = {
        "entities": [
            {"id": "PH_9855", "type": "Phone", "label": "Burner phone (forum post)"},
        ],
        "relationships": [
            {"source": "P_ARJUN", "target": "PH_9855", "relation": "OWNS", "confidence": 0.6},
            {"source": "PH_9855", "target": "PH_9811", "relation": "CALLED", "confidence": 0.5},
        ],
    }

    bank_logs = [
        {"txn_id": "T1", "from_account": "ACC_VICTIM_A", "to_account": "ACC_3003", "amount": 50000, "timestamp": "2026-09-03T10:00:00"},
        {"txn_id": "T2", "from_account": "ACC_VICTIM_B", "to_account": "ACC_3003", "amount": 75000, "timestamp": "2026-09-03T10:05:00"},
        {"txn_id": "T3", "from_account": "ACC_VICTIM_C", "to_account": "ACC_3003", "amount": 120000, "timestamp": "2026-09-03T10:20:00"},
        {"txn_id": "T4", "from_account": "ACC_3003", "to_account": "ACC_1001", "amount": 90000, "timestamp": "2026-09-03T11:00:00"},
        {"txn_id": "T5", "from_account": "ACC_3003", "to_account": "ACC_2002", "amount": 80000, "timestamp": "2026-09-03T11:05:00"},
        {"txn_id": "T6", "from_account": "ACC_3003", "to_account": "ACC_4004", "amount": 70000, "timestamp": "2026-09-03T11:10:00"},
        {"txn_id": "T7", "from_account": "ACC_1001", "to_account": "ACC_4004", "amount": 85000, "timestamp": "2026-09-03T12:00:00"},
        {"txn_id": "T8", "from_account": "ACC_2002", "to_account": "ACC_4004", "amount": 75000, "timestamp": "2026-09-03T12:10:00"},
        {"txn_id": "T9", "from_account": "ACC_4004", "to_account": "ACC_OFFSHORE", "amount": 200000, "timestamp": "2026-09-03T14:00:00"},
        {"txn_id": "T10", "from_account": "ACC_VICTIM_A", "to_account": "ACC_2002", "amount": 15000, "timestamp": "2026-09-04T09:00:00"},
    ]

    return offline_data, osint_data, bank_logs


# --------------------------------------------------------------------------- #
# Graph state (built once, lazily, thread-safe)
# --------------------------------------------------------------------------- #

_graph: Optional[nx.DiGraph] = None
_graph_lock = threading.Lock()


def get_graph() -> nx.DiGraph:
    """
    FastAPI dependency returning the shared investigation graph.

    The graph is built from the demo data on first access (double-checked
    locking keeps this safe under concurrent requests) and reused afterwards.
    """
    global _graph
    if _graph is None:
        with _graph_lock:
            if _graph is None:
                try:
                    offline_data, osint_data, bank_logs = _load_demo_sources()
                    _graph = build_investigation_graph(offline_data, osint_data, bank_logs)
                    logger.info(
                        "Demo graph initialised: %d nodes, %d edges",
                        _graph.number_of_nodes(), _graph.number_of_edges(),
                    )
                except Exception as exc:  # pragma: no cover - defensive
                    logger.exception("Failed to build investigation graph")
                    raise HTTPException(status_code=500, detail="Graph initialisation failed") from exc
    return _graph


def _run_analytics(fn, *args: Any, **kwargs: Any) -> Any:
    """Execute an analytics function, converting unexpected errors into HTTP 500."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        logger.exception("Analytics function %s failed", getattr(fn, "__name__", fn))
        raise HTTPException(status_code=500, detail=f"{getattr(fn, '__name__', 'analytics')} failed") from exc


# --------------------------------------------------------------------------- #
# 3. Endpoints
# --------------------------------------------------------------------------- #

@router.get(
    "/",
    response_model=GraphResponse,
    summary="Full network graph",
    description="Returns every node and edge in the frontend-ready {nodes, edges} format.",
)
def get_network_graph(G: nx.DiGraph = Depends(get_graph)) -> dict:
    return _run_analytics(export_graph_for_ui, G)


@router.get(
    "/freeze-list",
    response_model=list[FreezeEntry],
    summary="Priority-sorted account freeze list",
    description="Bank accounts ordered by transaction flow; mule accounts are boosted.",
)
def get_freeze_list(
    limit: Optional[int] = Query(None, ge=1, le=1000, description="Return only the top N accounts"),
    min_throughput: float = Query(0.0, ge=0, description="Ignore accounts with flow at or below this amount"),
    G: nx.DiGraph = Depends(get_graph),
) -> list[dict]:
    result = _run_analytics(generate_freeze_list, G, min_throughput=min_throughput)
    return result[:limit] if limit else result


@router.get(
    "/mules",
    response_model=list[MuleEntry],
    summary="Detected mule accounts",
    description="Accounts with high fan-in and fan-out that pass funds straight through.",
)
def get_mules(
    min_in_degree: int = Query(2, ge=1, description="Minimum distinct senders"),
    min_out_degree: int = Query(2, ge=1, description="Minimum distinct recipients"),
    min_pass_through: float = Query(0.7, ge=0, le=1, description="Minimum pass-through ratio (0-1)"),
    G: nx.DiGraph = Depends(get_graph),
) -> list[dict]:
    return _run_analytics(
        detect_mules,
        G,
        min_in_degree=min_in_degree,
        min_out_degree=min_out_degree,
        min_pass_through=min_pass_through,
    )


@router.get(
    "/suspects",
    response_model=list[SuspectEntry],
    summary="Ranked suspects / masterminds",
    description="Person and Company nodes ranked by composite network centrality.",
)
def get_suspects(
    top_n: Optional[int] = Query(None, ge=1, le=500, description="Return only the top N suspects"),
    G: nx.DiGraph = Depends(get_graph),
) -> list[dict]:
    return _run_analytics(rank_suspects, G, top_n=top_n)