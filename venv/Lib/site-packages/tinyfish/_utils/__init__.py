"""Reusable SDK foundation.

Provides base classes for building HTTP API SDKs:
- Clients: HTTP client with auth, retries, error handling
- Resources: Containers for grouping related API methods
- Exceptions: Complete error hierarchy
"""

from .client import BaseAsyncAPIClient as BaseAsyncAPIClient
from .client import BaseSyncAPIClient as BaseSyncAPIClient
from .exceptions import APIConnectionError as APIConnectionError
from .exceptions import APIError as APIError
from .exceptions import APIStatusError as APIStatusError
from .exceptions import APITimeoutError as APITimeoutError
from .exceptions import AuthenticationError as AuthenticationError
from .exceptions import BadRequestError as BadRequestError
from .exceptions import ConflictError as ConflictError
from .exceptions import InternalServerError as InternalServerError
from .exceptions import NotFoundError as NotFoundError
from .exceptions import PermissionDeniedError as PermissionDeniedError
from .exceptions import RateLimitError as RateLimitError
from .exceptions import RequestTimeoutError as RequestTimeoutError
from .exceptions import SDKError as SDKError
from .exceptions import UnprocessableEntityError as UnprocessableEntityError
from .resource import BaseAsyncAPIResource as BaseAsyncAPIResource
from .resource import BaseSyncAPIResource as BaseSyncAPIResource
