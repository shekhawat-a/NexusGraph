"""Local multi-crime entity parsing and graph projection helpers."""

from __future__ import annotations

import ipaddress
import re
from collections import Counter
from typing import Any, Iterable

BTC_ADDRESS_RE = re.compile(
    r"\b(?:bc1[ac-hj-np-z02-9]{11,71}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})\b",
    re.IGNORECASE,
)
ETH_ADDRESS_RE = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
TRANSACTION_HASH_RE = re.compile(r"\b(?:0x[a-fA-F0-9]{64}|[a-fA-F0-9]{64})\b")
PHONE_RE = re.compile(r"(?<!\w)(?:\+?91[\s.-]?)?(?:\d[\s.-]?){10}(?!\w)")
DOMAIN_RE = re.compile(
    r"(?i)(?<![@\w-])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"(?:com|net|org|edu|gov|in|io|co|uk|dev|app|info|biz|xyz)\b"
)
IP_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
HANDLE_RE = re.compile(r"(?<![\w.])@([A-Za-z0-9_]{2,32})\b")

CATEGORY_RULES = {
    "crypto_fraud": re.compile(
        r"\b(?:crypto(?:currency)?|bitcoin|btc|ethereum|eth|usdt|wallet|"
        r"blockchain|transaction hash|txid)\b",
        re.IGNORECASE,
    ),
    "human_trafficking": re.compile(
        r"\b(?:human trafficking|trafficking|recruitment agency|placement agency|"
        r"forced labour|forced labor|transit|border crossing|missing worker)\b",
        re.IGNORECASE,
    ),
    "corporate_data_breach": re.compile(
        r"\b(?:data breach|data leak|credential exfiltration|exfiltrat\w*|"
        r"server log|compromised server|ransomware|credential dump)\b",
        re.IGNORECASE,
    ),
    "cyber_fraud_phishing": re.compile(
        r"\b(?:cyber fraud|phishing|smishing|vishing|upi|bank account|"
        r"mule account|online fraud|otp fraud)\b",
        re.IGNORECASE,
    ),
}

TRANSIT_RE = re.compile(
    r"\b(?:transit|travel|transport|border|crossed|route|recruited|placement)\b",
    re.IGNORECASE,
)
CREDENTIAL_RE = re.compile(
    r"\b(?:credential(?:s)?|password|login dump|token theft|exfiltrat\w*|"
    r"stealer|credential dump)\b",
    re.IGNORECASE,
)
SERVER_LOG_RE = re.compile(
    r"\b(?:access log|server log|authentication failure|http/\d(?:\.\d)?|"
    r"status code|failed login|request method)\b",
    re.IGNORECASE,
)
AGENCY_RE = re.compile(
    r"(?i)\b(?:recruitment|placement|employment|travel)\s+agency\s*[:=-]\s*"
    r"([^\n,;]{2,100})"
)
HOP_RE = re.compile(
    r"(?i)\b(?:from|sender)\s*[:=]?\s*"
    r"(0x[a-f0-9]{40}|0x[a-f0-9]{64}|[13][a-km-zA-HJ-NP-Z1-9]{25,34}|"
    r"bc1[ac-hj-np-z02-9]{11,71})\s*(?:to|->)\s*"
    r"(0x[a-f0-9]{40}|0x[a-f0-9]{64}|[13][a-km-zA-HJ-NP-Z1-9]{25,34}|"
    r"bc1[ac-hj-np-z02-9]{11,71})"
)


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def _lines_matching(text: str, pattern: re.Pattern[str], limit: int = 50) -> list[str]:
    return _unique(
        line.strip()[:300]
        for line in text.splitlines()
        if pattern.search(line)
    )[:limit]


def parse_multi_crime_entities(text: str) -> dict[str, Any]:
    """Extract local, deterministic indicators for the supported crime categories."""
    wallets = _unique(BTC_ADDRESS_RE.findall(text) + ETH_ADDRESS_RE.findall(text))
    transaction_hashes = _unique(TRANSACTION_HASH_RE.findall(text))

    phones = []
    for match in PHONE_RE.findall(text):
        digits = re.sub(r"\D", "", match)
        if len(digits) == 10:
            phones.append(digits)
        elif len(digits) == 12 and digits.startswith("91"):
            phones.append(digits[2:])
    phones = _unique(phones)
    shared_contacts = [
        phone for phone, count in Counter(
            re.sub(r"\D", "", match)[-10:] for match in PHONE_RE.findall(text)
        ).items() if count > 1
    ]

    ips = []
    for candidate in IP_RE.findall(text):
        try:
            ips.append(str(ipaddress.ip_address(candidate)))
        except ValueError:
            continue

    domains = _unique(DOMAIN_RE.findall(text))
    handles = _unique(HANDLE_RE.findall(text))
    upi_ids = _unique(re.findall(r"\b[A-Za-z0-9._-]+@[A-Za-z0-9._-]+\b", text))
    upi_names = {item.split("@", 1)[0].lower() for item in upi_ids}
    handles = [handle for handle in handles if handle.lower() not in upi_names]
    hops = [
        {"from": source, "to": target}
        for source, target in HOP_RE.findall(text)
        if source.lower() != target.lower()
    ]
    agencies = _unique(match.group(1).strip(" .") for match in AGENCY_RE.finditer(text))
    transit_logs = _lines_matching(text, TRANSIT_RE)
    server_log_indicators = _lines_matching(text, SERVER_LOG_RE)
    credential_indicators = _unique(
        match.group(0).lower() for match in CREDENTIAL_RE.finditer(text)
    )

    crime_categories = [
        category for category, pattern in CATEGORY_RULES.items() if pattern.search(text)
    ]
    if wallets or transaction_hashes or hops:
        crime_categories.append("crypto_fraud")
    if agencies or transit_logs:
        crime_categories.append("human_trafficking")
    if ips or domains or server_log_indicators or credential_indicators:
        if SERVER_LOG_RE.search(text) or CREDENTIAL_RE.search(text):
            crime_categories.append("corporate_data_breach")
    if phones or upi_ids or re.search(r"\b\d{12}\b", text):
        crime_categories.append("cyber_fraud_phishing")
    crime_categories = _unique(crime_categories)

    return {
        "crime_categories": crime_categories,
        "crypto_wallets": wallets,
        "crypto_transaction_hashes": transaction_hashes,
        "transaction_hops": hops,
        "transit_logs": transit_logs,
        "recruitment_agencies": agencies,
        "communication_handles": handles,
        "shared_contact_numbers": shared_contacts,
        "domains": domains,
        "ip_addresses": _unique(ips),
        "server_log_indicators": server_log_indicators,
        "credential_exfiltration_indicators": credential_indicators,
        "phone_numbers": phones,
        "bank_accounts": _unique(re.findall(r"\b\d{12}\b", text)),
        "upi_ids": upi_ids,
    }


def build_entity_graph(
    entities: dict[str, Any],
    document_id: str,
    document_name: str,
) -> dict[str, list[dict[str, Any]]]:
    """Project extracted indicators into an integration-ready graph payload."""
    nodes: dict[str, dict[str, Any]] = {
        document_id: {
            "id": document_id,
            "type": "Report",
            "label": document_name,
            "crime_categories": entities.get("crime_categories", []),
        }
    }
    edges: dict[tuple[str, str, str], dict[str, Any]] = {}

    field_types = {
        "crypto_wallets": ("CryptoWallet", "wallet"),
        "crypto_transaction_hashes": ("CryptoTransaction", "transaction_hash"),
        "phone_numbers": ("Phone", "phone"),
        "shared_contact_numbers": ("Phone", "phone"),
        "bank_accounts": ("BankAccount", "bank_account"),
        "upi_ids": ("UPI", "upi_id"),
        "communication_handles": ("SocialHandle", "handle"),
        "domains": ("Domain", "domain"),
        "ip_addresses": ("IPAddress", "ip_address"),
        "recruitment_agencies": ("RecruitmentAgency", "agency"),
        "transit_logs": ("TransitLog", "transit_log"),
        "server_log_indicators": ("ServerLogIndicator", "server_log_indicator"),
        "credential_exfiltration_indicators": ("CredentialIndicator", "credential_indicator"),
    }
    for field, (node_type, entity_kind) in field_types.items():
        for value in entities.get(field, []):
            identifier = str(value)
            node_id = f"{entity_kind}:{identifier}"
            nodes.setdefault(
                node_id,
                {
                    "id": node_id,
                    "type": node_type,
                    "label": identifier,
                    "value": identifier,
                    "crime_categories": entities.get("crime_categories", []),
                },
            )
            edge = (document_id, node_id, "MENTIONS")
            edges[edge] = {"source": edge[0], "target": edge[1], "relation": edge[2]}

    for hop in entities.get("transaction_hops", []):
        if not isinstance(hop, dict):
            continue
        source_wallet, target_wallet = hop.get("from"), hop.get("to")
        if not isinstance(source_wallet, str) or not isinstance(target_wallet, str):
            continue
        source_id = f"wallet:{source_wallet}"
        target_id = f"wallet:{target_wallet}"
        for wallet in (source_wallet, target_wallet):
            node_id = f"wallet:{wallet}"
            nodes.setdefault(
                node_id,
                {
                    "id": node_id,
                    "type": "CryptoWallet",
                    "label": wallet,
                    "value": wallet,
                    "crime_categories": ["crypto_fraud"],
                },
            )
        edge = (source_id, target_id, "TRANSFERRED_TO")
        edges[edge] = {
            "source": source_id,
            "target": target_id,
            "relation": "TRANSFERRED_TO",
            "evidence_document": document_id,
        }

    return {"nodes": list(nodes.values()), "edges": list(edges.values())}


def link_entities_across_reports(
    reports: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return shared-contact links for report stores that provide parsed reports."""
    contact_reports: dict[str, set[str]] = {}
    for report in reports:
        report_id = str(report.get("document_id", "")).strip()
        if not report_id:
            continue
        entities = report.get("entities", report.get("ai_extracted_entities", {}))
        for number in _unique(
            list(entities.get("phone_numbers", []))
            + list(entities.get("shared_contact_numbers", []))
        ):
            normalized_number = re.sub(r"\D", "", str(number))
            if len(normalized_number) == 12 and normalized_number.startswith("91"):
                normalized_number = normalized_number[2:]
            if len(normalized_number) == 10:
                contact_reports.setdefault(normalized_number, set()).add(report_id)

    return [
        {
            "source": f"report:{report_id}",
            "target": f"report:{other_report_id}",
            "relation": "SHARES_CONTACT",
            "contact_number": number,
        }
        for number, report_ids in contact_reports.items()
        if len(report_ids) > 1
        for report_id in sorted(report_ids)
        for other_report_id in sorted(report_ids)
        if report_id < other_report_id
    ]
