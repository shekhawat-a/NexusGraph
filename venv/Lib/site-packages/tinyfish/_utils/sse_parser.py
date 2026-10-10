"""Simple Server-Sent Events (SSE) parser."""

import json
from collections.abc import AsyncIterator, Iterator
from typing import Any

from .exceptions import SSEParseError

_DATA_PREFIX = "data:"


def parse_sse_line_stream(lines: Iterator[str]) -> Iterator[dict[str, Any]]:
    """
    Parse SSE stream and yield JSON event data.

    SSE Format:
        event: STARTED
        data: {"type":"STARTED","run_id":"123",...}

        event: PROGRESS
        data: {"type":"PROGRESS",...}

    Yields:
        Parsed JSON objects from 'data:' lines
    """
    for line in lines:
        line = line.strip()

        # Skip empty lines and comments
        if not line or line.startswith(":"):
            continue

        # Parse data lines (the actual event payload)
        if line.startswith("data:"):
            data_str = line[len(_DATA_PREFIX) :].strip()  # Remove 'data:' prefix

            try:
                event_data = json.loads(data_str)
                yield event_data
            except json.JSONDecodeError as e:
                raise SSEParseError(f"Malformed JSON in SSE event: {e}", line=line) from e

        # Ignore 'event:', 'id:', 'retry:' lines for now
        # (we get event type from the JSON data itself)


async def async_parse_sse_line_stream(lines: AsyncIterator[str]) -> AsyncIterator[dict[str, Any]]:
    """Async version of parse_sse_line_stream."""
    async for line in lines:
        line = line.strip()

        if not line or line.startswith(":"):
            continue

        if line.startswith("data:"):
            data_str = line[len(_DATA_PREFIX) :].strip()

            try:
                event_data = json.loads(data_str)
                yield event_data
            except json.JSONDecodeError as e:
                raise SSEParseError(f"Malformed JSON in SSE event: {e}", line=line) from e
