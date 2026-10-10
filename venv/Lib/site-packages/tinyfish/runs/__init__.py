"""Runs resource for retrieving and listing automation runs."""

from __future__ import annotations

from tinyfish._utils.resource import BaseAsyncAPIResource, BaseSyncAPIResource

from .types import RunListResponse, RunRetrieveResponse, RunStatus, SortDirection


class RunsResource(BaseSyncAPIResource):
    """Retrieve and list automation runs."""

    def get(self, run_id: str) -> RunRetrieveResponse:
        """Retrieve a single run by its ID.

        Args:
            run_id: The run ID returned by `agent.queue()` or any run response.

        Returns:
            RunRetrieveResponse with the full run details including status and result.

        Raises:
            ValueError: run_id is empty or whitespace.
            NotFoundError: No run exists with that ID.
            AuthenticationError: Invalid API key.
        """
        if not run_id or not run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        return self._get(f"/v1/runs/{run_id}", cast_to=RunRetrieveResponse)

    def list(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        status: RunStatus | None = None,
        goal: str | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        sort_direction: SortDirection | None = None,
    ) -> RunListResponse:
        """List automation runs, with optional filtering and pagination.

        Args:
            cursor: Pagination cursor from a previous response's next_cursor field.
            limit: Maximum number of runs to return.
            status: Filter by run status — one of "PENDING", "RUNNING",
                    "COMPLETED", "FAILED", or "CANCELLED".
            goal: Filter by goal text.
            created_after: Filter runs created after this ISO timestamp.
            created_before: Filter runs created before this ISO timestamp.
            sort_direction: Sort order — "asc" or "desc".

        Returns:
            RunListResponse with a list of runs and pagination info.

        Raises:
            AuthenticationError: Invalid API key.
        """
        params = {}
        if cursor is not None:
            params["cursor"] = cursor
        if limit is not None:
            params["limit"] = limit
        if status is not None:
            params["status"] = status
        if goal is not None:
            params["goal"] = goal
        if created_after is not None:
            params["created_after"] = created_after
        if created_before is not None:
            params["created_before"] = created_before
        if sort_direction is not None:
            params["sort_direction"] = sort_direction
        return self._get("/v1/runs", params=params, cast_to=RunListResponse)


class AsyncRunsResource(BaseAsyncAPIResource):
    """Async retrieve and list automation runs."""

    async def get(self, run_id: str) -> RunRetrieveResponse:
        """Retrieve a single run by its ID.

        Async version of `RunsResource.get()`.

        Args:
            run_id: The run ID returned by `agent.queue()` or any run response.

        Returns:
            RunRetrieveResponse with the full run details including status and result.

        Raises:
            ValueError: run_id is empty or whitespace.
            NotFoundError: No run exists with that ID.
            AuthenticationError: Invalid API key.
        """
        if not run_id or not run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        return await self._get(f"/v1/runs/{run_id}", cast_to=RunRetrieveResponse)

    async def list(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        status: RunStatus | None = None,
        goal: str | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        sort_direction: SortDirection | None = None,
    ) -> RunListResponse:
        """List automation runs, with optional filtering and pagination.

        Async version of `RunsResource.list()`.

        Args:
            cursor: Pagination cursor from a previous response's next_cursor field.
            limit: Maximum number of runs to return.
            status: Filter by run status — one of "PENDING", "RUNNING",
                    "COMPLETED", "FAILED", or "CANCELLED".
            goal: Filter by goal text.
            created_after: Filter runs created after this ISO timestamp.
            created_before: Filter runs created before this ISO timestamp.
            sort_direction: Sort order — "asc" or "desc".

        Returns:
            RunListResponse with a list of runs and pagination info.

        Raises:
            AuthenticationError: Invalid API key.
        """
        params = {}
        if cursor is not None:
            params["cursor"] = cursor
        if limit is not None:
            params["limit"] = limit
        if status is not None:
            params["status"] = status
        if goal is not None:
            params["goal"] = goal
        if created_after is not None:
            params["created_after"] = created_after
        if created_before is not None:
            params["created_before"] = created_before
        if sort_direction is not None:
            params["sort_direction"] = sort_direction
        return await self._get("/v1/runs", params=params, cast_to=RunListResponse)
