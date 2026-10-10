"""
graph_engine.py
===============
Quantum Veil - Financial Cybercrime Investigation Platform
Graph analytics engine.

Responsibilities
----------------
1. Fuse offline (seized/CDR/registry), OSINT, and bank-log data into a single
   directed investigation graph (nx.DiGraph).
2. Run analytics: mule-account detection, suspect ranking (centrality),
   and prioritised account freeze list.
3. Export the graph as UI-friendly JSON: {"nodes": [...], "edges": [...]}.

Expected input shapes
---------------------
offline_data = {
    "persons":      [{"id": str, "name": str, ...}],
    "phones":       [{"id": str, "owner": <person id, optional>, ...}],
    "companies":    [{"id": str, "name": str, ...}],
    "bank_accounts":[{"id": str, "owner": <person/company id, optional>, ...}],
    "call_records": [{"caller": str, "callee": str, "duration_sec": int, "timestamp": str}],
    "directorships":[{"person": str, "company": str}],
}

osint_data = {
    "entities":      [{"id": str, "type": str, "label": str, ...}],
    "relationships": [{"source": str, "target": str, "relation": str, ...}],
}

bank_logs = [
    {"txn_id": str, "from_account": str, "to_account": str,
     "amount": float, "timestamp": str},
    ...
]
"""

from __future__ import annotations

import json
import logging
from typing import Any

import networkx as nx
import pandas as pd

logger = logging.getLogger("quantum_veil.graph_engine")

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

# Node types supported by the platform.
# Node types supported by the platform
NODE_TYPES = {
    "Person", "Phone", "BankAccount", "Company", "CryptoWallet", "CryptoTransaction",
    "SocialHandle", "IPAddress", "Email", "UPI", "Domain", "TransitLog",
    "RecruitmentAgency", "ServerLogIndicator", "CredentialIndicator", "Report",
}

# Relation names used on edges
REL_CALLED = "CALLED"
REL_TRANSFERRED = "TRANSFERRED"
REL_DIRECTOR_OF = "DIRECTOR_OF"
REL_OWNS = "OWNS"
REL_LOGGED_IN = "LOGGED_IN_FROM"  # For IP Addresses
REL_MESSAGED = "MESSAGED"        # For Social Handles

# Source labels (provenance of each node/edge).
SRC_OFFLINE = "offline"
SRC_OSINT = "osint"
SRC_BANK = "bank_logs"


# --------------------------------------------------------------------------- #
# 1. Graph initialisation
# --------------------------------------------------------------------------- #

def create_graph() -> nx.DiGraph:
    """Create an empty directed investigation graph."""
    return nx.DiGraph(name="QuantumVeilInvestigationGraph")


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

def _merge_source(existing: str | None, new: str) -> str:
    """Merge provenance labels into a sorted, comma-separated string."""
    parts = set(filter(None, (existing or "").split(",")))
    parts.add(new)
    return ",".join(sorted(p.strip() for p in parts))


def _add_node(G: nx.DiGraph, node_id: Any, node_type: str, source: str, **attrs: Any) -> None:
    """
    Add a node or enrich an existing one.

    - 'id', 'type' and 'source' are always set.
    - If the node already exists, provenance is merged and new attributes are
      added without overwriting known non-empty values.
    - A concrete type is never downgraded to 'Unknown'.
    """
    if node_id is None or str(node_id).strip() == "":
        logger.warning("Skipping node with empty id (source=%s)", source)
        return

    node_id = str(node_id)
    node_type = node_type if node_type in NODE_TYPES else "Unknown"

    if G.has_node(node_id):
        data = G.nodes[node_id]
        if data.get("type", "Unknown") == "Unknown" and node_type != "Unknown":
            data["type"] = node_type
        data["source"] = _merge_source(data.get("source"), source)
        for k, v in attrs.items():
            if v not in (None, "") and data.get(k) in (None, ""):
                data[k] = v
    else:
        G.add_node(node_id, id=node_id, type=node_type, source=source, **attrs)


def _ensure_node(G: nx.DiGraph, node_id: Any, default_type: str, source: str) -> str | None:
    """Make sure a node exists (creating a placeholder if needed); return its id."""
    if node_id is None or str(node_id).strip() == "":
        return None
    node_id = str(node_id)
    if not G.has_node(node_id):
        _add_node(G, node_id, default_type, source)
    return node_id


def _add_edge(G: nx.DiGraph, src: Any, dst: Any, relation: str, source: str, **attrs: Any) -> None:
    """
    Add an edge, or merge into an existing one.

    nx.DiGraph holds a single edge per (src, dst) pair, so repeated events
    (many calls / many transfers) are aggregated:
      - TRANSFERRED : 'total_amount', 'txn_count' are accumulated.
      - CALLED      : 'call_count', 'total_duration_sec' are accumulated.
    If a different relation already links the same pair, it is recorded in the
    'relations' list while 'relation' keeps the primary (first-seen) value.
    """
    if src is None or dst is None:
        return
    src, dst = str(src), str(dst)
    if src == dst:
        logger.debug("Ignoring self-loop on %s (%s)", src, relation)
        return

    amount = float(attrs.pop("amount", 0.0) or 0.0)
    duration = int(attrs.pop("duration_sec", 0) or 0)
    timestamp = attrs.pop("timestamp", None)

    if G.has_edge(src, dst):
        edge = G[src][dst]
        edge["source"] = _merge_source(edge.get("source"), source)
        relations = edge.setdefault("relations", [edge["relation"]])
        if relation not in relations:
            relations.append(relation)
    else:
        G.add_edge(src, dst, relation=relation, relations=[relation], source=source)
        edge = G[src][dst]

    if relation == REL_TRANSFERRED:
        edge["total_amount"] = round(edge.get("total_amount", 0.0) + amount, 2)
        edge["txn_count"] = edge.get("txn_count", 0) + 1
    elif relation == REL_CALLED:
        edge["call_count"] = edge.get("call_count", 0) + 1
        edge["total_duration_sec"] = edge.get("total_duration_sec", 0) + duration

    if timestamp:
        ts = str(timestamp)
        edge["first_seen"] = min(edge.get("first_seen", ts), ts)
        edge["last_seen"] = max(edge.get("last_seen", ts), ts)

    for k, v in attrs.items():
        if v not in (None, "") and k not in edge:
            edge[k] = v


# --------------------------------------------------------------------------- #
# 2. Graph construction
# --------------------------------------------------------------------------- #

def build_investigation_graph(offline_data: dict, osint_data: dict, bank_logs: list) -> nx.DiGraph:
    """
    Fuse all intelligence sources into one directed graph.

    Parameters
    ----------
    offline_data : dict   Registry / CDR / seized-device data (see module docstring).
    osint_data   : dict   Open-source intelligence entities and relationships.
    bank_logs    : list   Bank transaction records.

    Returns
    -------
    nx.DiGraph with typed nodes (id, type, source) and relation-labelled edges.
    """
    G = create_graph()
    offline_data = offline_data or {}
    osint_data = osint_data or {}
    bank_logs = bank_logs or []

    # ---------------- Offline data ---------------- #
    for p in offline_data.get("persons", []):
        extra = {k: v for k, v in p.items() if k not in ("id", "type", "source")}
        _add_node(G, p.get("id"), "Person", SRC_OFFLINE, **extra)

    for c in offline_data.get("companies", []):
        extra = {k: v for k, v in c.items() if k not in ("id", "type", "source")}
        _add_node(G, c.get("id"), "Company", SRC_OFFLINE, **extra)

    for ph in offline_data.get("phones", []):
        extra = {k: v for k, v in ph.items() if k not in ("id", "type", "source", "owner")}
        _add_node(G, ph.get("id"), "Phone", SRC_OFFLINE, **extra)
        owner = _ensure_node(G, ph.get("owner"), "Person", SRC_OFFLINE)
        if owner:
            _add_edge(G, owner, ph.get("id"), REL_OWNS, SRC_OFFLINE)

    for acc in offline_data.get("bank_accounts", []):
        extra = {k: v for k, v in acc.items() if k not in ("id", "type", "source", "owner")}
        _add_node(G, acc.get("id"), "BankAccount", SRC_OFFLINE, **extra)
        owner = _ensure_node(G, acc.get("owner"), "Person", SRC_OFFLINE)
        if owner:
            _add_edge(G, owner, acc.get("id"), REL_OWNS, SRC_OFFLINE)

    for call in offline_data.get("call_records", []):
        caller = _ensure_node(G, call.get("caller"), "Phone", SRC_OFFLINE)
        callee = _ensure_node(G, call.get("callee"), "Phone", SRC_OFFLINE)
        _add_edge(
            G, caller, callee, REL_CALLED, SRC_OFFLINE,
            duration_sec=call.get("duration_sec", 0),
            timestamp=call.get("timestamp"),
        )

    for d in offline_data.get("directorships", []):
        person = _ensure_node(G, d.get("person"), "Person", SRC_OFFLINE)
        company = _ensure_node(G, d.get("company"), "Company", SRC_OFFLINE)
        _add_edge(G, person, company, REL_DIRECTOR_OF, SRC_OFFLINE)

    # ---------------- OSINT data ---------------- #
    for ent in osint_data.get("entities", []):
        extra = {k: v for k, v in ent.items() if k not in ("id", "type", "source")}
        _add_node(G, ent.get("id"), ent.get("type", "Unknown"), SRC_OSINT, **extra)

    for rel in osint_data.get("relationships", []):
        src = _ensure_node(G, rel.get("source"), "Unknown", SRC_OSINT)
        dst = _ensure_node(G, rel.get("target"), "Unknown", SRC_OSINT)
        extra = {k: v for k, v in rel.items() if k not in ("source", "target", "relation")}
        _add_edge(G, src, dst, str(rel.get("relation", "RELATED_TO")).upper(), SRC_OSINT, **extra)

    # ---------------- Bank logs ---------------- #
    for txn in bank_logs:
        try:
            amount = float(txn.get("amount", 0.0))
        except (TypeError, ValueError):
            logger.warning("Skipping txn with invalid amount: %s", txn)
            continue
        frm = _ensure_node(G, txn.get("from_account"), "BankAccount", SRC_BANK)
        to = _ensure_node(G, txn.get("to_account"), "BankAccount", SRC_BANK)
        # Bank logs are authoritative that these IDs are accounts.
        for acc_id in (frm, to):
            if acc_id:
                _add_node(G, acc_id, "BankAccount", SRC_BANK)
        _add_edge(
            G, frm, to, REL_TRANSFERRED, SRC_BANK,
            amount=amount, timestamp=txn.get("timestamp"),
        )

    logger.info("Graph built: %d nodes, %d edges", G.number_of_nodes(), G.number_of_edges())
    return G


# --------------------------------------------------------------------------- #
# Analytics helpers
# --------------------------------------------------------------------------- #

def _transfer_stats(G: nx.DiGraph) -> pd.DataFrame:
    """
    Per-BankAccount transfer statistics derived from TRANSFERRED edges only.

    Columns: account_id, in_degree, out_degree, total_in, total_out,
             txn_in, txn_out, throughput
    """
    rows = []
    for node, data in G.nodes(data=True):
        if data.get("type") not in ("BankAccount", "CryptoWallet"):
            continue
        in_edges = [(u, d) for u, _, d in G.in_edges(node, data=True)
                    if REL_TRANSFERRED in d.get("relations", [d.get("relation")])]
        out_edges = [(v, d) for _, v, d in G.out_edges(node, data=True)
                     if REL_TRANSFERRED in d.get("relations", [d.get("relation")])]
        total_in = sum(d.get("total_amount", 0.0) for _, d in in_edges)
        total_out = sum(d.get("total_amount", 0.0) for _, d in out_edges)
        rows.append({
            "account_id": node,
            "in_degree": len(in_edges),
            "out_degree": len(out_edges),
            "total_in": round(total_in, 2),
            "total_out": round(total_out, 2),
            "txn_in": sum(d.get("txn_count", 0) for _, d in in_edges),
            "txn_out": sum(d.get("txn_count", 0) for _, d in out_edges),
            "throughput": round(total_in + total_out, 2),
        })
    cols = ["account_id", "in_degree", "out_degree", "total_in", "total_out",
            "txn_in", "txn_out", "throughput"]
    return pd.DataFrame(rows, columns=cols)


def _minmax(series: pd.Series) -> pd.Series:
    """Min-max normalise a series to [0, 1]; constant series map to 0."""
    if series.empty:
        return series
    rng = series.max() - series.min()
    if rng == 0:
        return pd.Series(0.0, index=series.index)
    return (series - series.min()) / rng


# --------------------------------------------------------------------------- #
# 3a. Mule detection
# --------------------------------------------------------------------------- #

def detect_mules(
    G: nx.DiGraph,
    min_in_degree: int = 2,
    min_out_degree: int = 2,
    min_pass_through: float = 0.7,
) -> list[dict]:
    """
    Identify likely money-mule BankAccount nodes.

    A mule typically receives funds from MANY sources and quickly forwards them
    to MANY destinations, retaining little. An account is flagged when:
        * in_degree  >= min_in_degree   (distinct senders)
        * out_degree >= min_out_degree  (distinct recipients)
        * pass-through ratio = min(in, out) / max(in, out) >= min_pass_through

    Returns a list of dicts sorted by 'mule_score' (descending).
    """
    stats = _transfer_stats(G)
    if stats.empty:
        return []

    mask = (stats["in_degree"] >= min_in_degree) & (stats["out_degree"] >= min_out_degree)
    candidates = stats[mask].copy()
    if candidates.empty:
        return []

    hi = candidates[["total_in", "total_out"]].max(axis=1).replace(0, float("nan"))
    lo = candidates[["total_in", "total_out"]].min(axis=1)
    candidates["pass_through_ratio"] = (lo / hi).fillna(0.0).round(3)
    candidates = candidates[candidates["pass_through_ratio"] >= min_pass_through].copy()
    if candidates.empty:
        return []

    # Score = fan-in/fan-out balance (geometric mean) x pass-through x log-ish volume weight.
    fan = (candidates["in_degree"] * candidates["out_degree"]) ** 0.5
    candidates["mule_score"] = (
        fan * candidates["pass_through_ratio"] * (1 + _minmax(candidates["throughput"]))
    ).round(3)

    candidates = candidates.sort_values("mule_score", ascending=False)
    return candidates.to_dict(orient="records")


# --------------------------------------------------------------------------- #
# 3b. Suspect ranking
# --------------------------------------------------------------------------- #

def rank_suspects(G: nx.DiGraph, top_n: int | None = None) -> list[dict]:
    """
    Rank Person and Company nodes by network importance.

    Composite score (each metric min-max normalised):
        0.35 * PageRank           - influence via inbound links
        0.35 * Betweenness        - brokerage between otherwise separate clusters
        0.15 * In-degree centrality
        0.15 * Out-degree centrality

    Because Persons/Companies are rarely linked directly (they connect through
    phones, accounts and directorships), centrality is computed on the FULL
    graph and then filtered to Person/Company nodes.
    """
    if G.number_of_nodes() == 0:
        return []

    try:
        pagerank = nx.pagerank(G, weight=None)
    except Exception as exc:  # e.g. scipy missing or no convergence
        logger.warning("PageRank failed (%s); falling back to degree centrality.", exc)
        pagerank = nx.degree_centrality(G)

    betweenness = nx.betweenness_centrality(G, normalized=True)
    in_deg = nx.in_degree_centrality(G)
    out_deg = nx.out_degree_centrality(G)

    rows = []
    for node, data in G.nodes(data=True):
        if data.get("type") not in ("Person", "Company"):
            continue
        rows.append({
            "id": node,
            "type": data.get("type"),
            "name": data.get("name", data.get("label", node)),
            "pagerank": pagerank.get(node, 0.0),
            "betweenness": betweenness.get(node, 0.0),
            "in_centrality": in_deg.get(node, 0.0),
            "out_centrality": out_deg.get(node, 0.0),
        })

    if not rows:
        return []

    df = pd.DataFrame(rows)
    df["suspect_score"] = (
        0.35 * _minmax(df["pagerank"])
        + 0.35 * _minmax(df["betweenness"])
        + 0.15 * _minmax(df["in_centrality"])
        + 0.15 * _minmax(df["out_centrality"])
    ).round(4)

    for col in ("pagerank", "betweenness", "in_centrality", "out_centrality"):
        df[col] = df[col].round(4)

    df = df.sort_values(["suspect_score", "pagerank"], ascending=False).reset_index(drop=True)
    df.insert(0, "rank", df.index + 1)
    if top_n:
        df = df.head(top_n)
    return df.to_dict(orient="records")


# --------------------------------------------------------------------------- #
# 3c. Freeze list
# --------------------------------------------------------------------------- #

def generate_freeze_list(G: nx.DiGraph, min_throughput: float = 0.0) -> list[dict]:
    """
    Produce a priority-sorted list of bank accounts to freeze.

    Priority is driven by transaction flow:
        * throughput  (total_in + total_out) is the base measure,
        * accounts flagged by detect_mules() receive a 1.5x multiplier,
          since freezing a pass-through hub interrupts the most laundering paths.

    Returns a list of dicts sorted by 'priority_score' descending.
    """
    stats = _transfer_stats(G)
    if stats.empty:
        return []

    stats = stats[stats["throughput"] > min_throughput].copy()
    if stats.empty:
        return []

    mule_ids = {m["account_id"] for m in detect_mules(G)}
    stats["is_mule"] = stats["account_id"].isin(mule_ids)
    stats["priority_score"] = (
        stats["throughput"] * stats["is_mule"].map({True: 1.5, False: 1.0})
    ).round(2)

    # Attach owner (if known) from OWNS edges for the investigator's convenience.
    def _owner(acc: str) -> str | None:
        for pred in G.predecessors(acc):
            if G[pred][acc].get("relation") == REL_OWNS or REL_OWNS in G[pred][acc].get("relations", []):
                return pred
        return None

    # Cast to object so unknown owners stay None (not NaN) and remain JSON-safe.
    stats["owner"] = stats["account_id"].map(_owner).astype(object)
    stats["owner"] = stats["owner"].where(stats["owner"].notna(), None)

    stats = stats.sort_values(["priority_score", "throughput"], ascending=False).reset_index(drop=True)
    stats.insert(0, "priority", stats.index + 1)
    return stats.to_dict(orient="records")


# --------------------------------------------------------------------------- #
# 4. UI export
# --------------------------------------------------------------------------- #

def _json_safe(value: Any) -> Any:
    """Coerce values (sets, numpy scalars, etc.) into JSON-serialisable types."""
    if isinstance(value, (set, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if hasattr(value, "item"):  # numpy scalar
        return value.item()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def export_graph_for_ui(G: nx.DiGraph) -> dict:
    """
    Convert the graph into a front-end friendly dictionary:

        {"nodes": [{"id", "type", "source", "label", ...attrs}],
         "edges": [{"source", "target", "relation", ...attrs}]}
    """
    nodes = []
    for node_id, data in G.nodes(data=True):
        item = {
            "id": node_id,
            "type": data.get("type", "Unknown"),
            "source": data.get("source", ""),
            "label": data.get("name") or data.get("label") or node_id,
        }
        for k, v in data.items():
            if k not in item:
                item[k] = v
        nodes.append(_json_safe(item))

    edges = []
    for u, v, data in G.edges(data=True):
        item = {"source": u, "target": v, "relation": data.get("relation", "RELATED_TO")}
        for k, val in data.items():
            if k not in item:
                item[k] = val
        edges.append(_json_safe(item))

    return {"nodes": nodes, "edges": edges}


# --------------------------------------------------------------------------- #
# 5. Local test harness
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    mock_offline = {
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

    mock_osint = {
        "entities": [
            {"id": "PH_9855", "type": "Phone", "label": "Burner phone (forum post)"},
        ],
        "relationships": [
            {"source": "P_ARJUN", "target": "PH_9855", "relation": "OWNS", "confidence": 0.6},
            {"source": "PH_9855", "target": "PH_9811", "relation": "CALLED", "confidence": 0.5},
        ],
    }

    mock_bank_logs = [
        # Victims / sources feeding the mule account ACC_3003
        {"txn_id": "T1", "from_account": "ACC_VICTIM_A", "to_account": "ACC_3003", "amount": 50000, "timestamp": "2026-09-03T10:00:00"},
        {"txn_id": "T2", "from_account": "ACC_VICTIM_B", "to_account": "ACC_3003", "amount": 75000, "timestamp": "2026-09-03T10:05:00"},
        {"txn_id": "T3", "from_account": "ACC_VICTIM_C", "to_account": "ACC_3003", "amount": 120000, "timestamp": "2026-09-03T10:20:00"},
        # Rapid fan-out from ACC_3003
        {"txn_id": "T4", "from_account": "ACC_3003", "to_account": "ACC_1001", "amount": 90000, "timestamp": "2026-09-03T11:00:00"},
        {"txn_id": "T5", "from_account": "ACC_3003", "to_account": "ACC_2002", "amount": 80000, "timestamp": "2026-09-03T11:05:00"},
        {"txn_id": "T6", "from_account": "ACC_3003", "to_account": "ACC_4004", "amount": 70000, "timestamp": "2026-09-03T11:10:00"},
        # Layering onward
        {"txn_id": "T7", "from_account": "ACC_1001", "to_account": "ACC_4004", "amount": 85000, "timestamp": "2026-09-03T12:00:00"},
        {"txn_id": "T8", "from_account": "ACC_2002", "to_account": "ACC_4004", "amount": 75000, "timestamp": "2026-09-03T12:10:00"},
        {"txn_id": "T9", "from_account": "ACC_4004", "to_account": "ACC_OFFSHORE", "amount": 200000, "timestamp": "2026-09-03T14:00:00"},
        {"txn_id": "T10", "from_account": "ACC_VICTIM_A", "to_account": "ACC_2002", "amount": 15000, "timestamp": "2026-09-04T09:00:00"},
    ]

    graph = build_investigation_graph(mock_offline, mock_osint, mock_bank_logs)

    print("\n=== DETECTED MULES ===")
    for m in detect_mules(graph):
        print(m)

    print("\n=== SUSPECT RANKING ===")
    for s in rank_suspects(graph):
        print(s)

    print("\n=== FREEZE LIST (sorted by priority) ===")
    freeze_list = generate_freeze_list(graph)
    for entry in freeze_list:
        print(entry)

    print("\n=== UI EXPORT JSON ===")
    print(json.dumps(export_graph_for_ui(graph), indent=2))