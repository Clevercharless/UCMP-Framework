"""
repository.databricks_workspace
================================

Databricks Workspace API adapter used by UCMP.

Supports two authentication modes:

1. Explicit bearer token
   - Used for external/local execution.
   - Preserves the original REST API behavior.

2. Native Databricks SDK authentication
   - Used when UCMP runs inside a Databricks workspace.
   - Uses WorkspaceClient() and the current authenticated identity.
   - Does not require a PAT when native Databricks authentication is available.

This module is discovery/export only.
It does NOT perform migration, replacement, or deployment.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request

from dataclasses import dataclass
from typing import Dict, List, Optional

from common.exceptions import RepositoryError
from common.logging_config import get_logger


logger = get_logger(__name__)


@dataclass(frozen=True)
class WorkspaceObject:
    """Minimal metadata returned by the Databricks Workspace API."""

    object_id: int
    path: str
    object_type: str
    language: Optional[str] = None
    size: Optional[int] = None
    modified_at: Optional[int] = None


class DatabricksWorkspaceClient:
    """
    Minimal Databricks Workspace client.

    If access_token is supplied:
        Use the existing REST API implementation.

    If access_token is not supplied:
        Use the native Databricks SDK WorkspaceClient().
    """

    def __init__(
        self,
        workspace_url: Optional[str] = None,
        access_token: Optional[str] = None,
        timeout: int = 30,
    ):
        self._base_url = (workspace_url or "").rstrip("/")
        self._access_token = access_token
        self._timeout = timeout
        self._sdk_client = None

        # ------------------------------------------------------------
        # Authentication mode 1:
        # Explicit bearer token
        # ------------------------------------------------------------
        if access_token:

            if not workspace_url:
                raise RepositoryError(
                    "Databricks workspace URL is required when using "
                    "token-based authentication"
                )

            logger.info(
                "DatabricksWorkspaceClient using explicit "
                "bearer-token authentication"
            )

        # ------------------------------------------------------------
        # Authentication mode 2:
        # Native Databricks SDK authentication
        # ------------------------------------------------------------
        else:

            try:
                from databricks.sdk import WorkspaceClient

                self._sdk_client = WorkspaceClient()

                logger.info(
                    "DatabricksWorkspaceClient using native "
                    "Databricks SDK authentication"
                )

            except Exception as exc:

                raise RepositoryError(
                    "No Databricks access token was supplied and native "
                    "Databricks SDK authentication could not be initialized: "
                    f"{exc}"
                ) from exc

    # -----------------------------------------------------------------
    # Workspace listing
    # -----------------------------------------------------------------

    def list(self, path: str = "/") -> List[WorkspaceObject]:
        """
        List direct children of a Databricks workspace path.
        """

        # Native SDK path
        if self._sdk_client is not None:
            return self._sdk_list(path)

        # REST API path
        payload = self._request(
            "GET",
            "/api/2.0/workspace/list",
            {"path": path},
        )

        objects = payload.get("objects", [])

        result: List[WorkspaceObject] = []

        for obj in objects:

            object_type_value = obj.get(
                "object_type",
                "",
            )

            # Normalize enum-like values if present.
            if hasattr(object_type_value, "value"):
                object_type_value = object_type_value.value

            object_type_value = str(object_type_value)

            result.append(
                WorkspaceObject(
                    object_id=int(
                        obj.get(
                            "object_id",
                            0,
                        )
                    ),
                    path=str(
                        obj.get(
                            "path",
                            "",
                        )
                    ),
                    object_type=object_type_value,
                    language=obj.get("language"),
                    size=obj.get("size"),
                    modified_at=obj.get("modified_at"),
                )
            )

        return result

    # -----------------------------------------------------------------
    # Native Databricks SDK listing
    # -----------------------------------------------------------------

    def _sdk_list(
        self,
        path: str,
    ) -> List[WorkspaceObject]:
        """
        List workspace objects using the native Databricks SDK.
        """

        try:

            objects = self._sdk_client.workspace.list(path)

            result: List[WorkspaceObject] = []

            for obj in objects:

                # Databricks SDK returns enum objects such as:
                #
                #   ObjectType.DIRECTORY
                #   ObjectType.NOTEBOOK
                #   ObjectType.FILE
                #
                # We normalize these to their underlying value where
                # possible so the rest of UCMP can compare them reliably.

                object_type_value = getattr(
                    obj,
                    "object_type",
                    "",
                )

                if hasattr(
                    object_type_value,
                    "value",
                ):
                    object_type_value = object_type_value.value

                object_type_value = str(
                    object_type_value
                )

                language_value = getattr(
                    obj,
                    "language",
                    None,
                )

                if language_value is not None:

                    if hasattr(
                        language_value,
                        "value",
                    ):
                        language_value = language_value.value

                    language_value = str(
                        language_value
                    )

                result.append(
                    WorkspaceObject(
                        object_id=int(
                            getattr(
                                obj,
                                "object_id",
                                0,
                            )
                            or 0
                        ),
                        path=str(
                            getattr(
                                obj,
                                "path",
                                "",
                            )
                            or ""
                        ),
                        object_type=object_type_value,
                        language=language_value,
                        size=getattr(
                            obj,
                            "size",
                            None,
                        ),
                        modified_at=getattr(
                            obj,
                            "modified_at",
                            None,
                        ),
                    )
                )

            return result

        except Exception as exc:

            raise RepositoryError(
                "Databricks SDK workspace listing failed "
                f"for '{path}': {exc}"
            ) from exc

    # -----------------------------------------------------------------
    # Recursive workspace discovery
    # -----------------------------------------------------------------

    def list_recursive(
        self,
        root_path: str = "/",
    ) -> List[WorkspaceObject]:
        """
        Recursively list workspace objects below root_path.
        """

        result: List[WorkspaceObject] = []

        pending: List[str] = [
            root_path
        ]

        while pending:

            current = pending.pop()

            try:

                children = self.list(
                    current
                )

            except RepositoryError as exc:

                raise RepositoryError(
                    "Unable to list Databricks workspace path "
                    f"'{current}': {exc}"
                ) from exc

            for obj in children:

                result.append(obj)

                object_type = (
                    obj.object_type or ""
                ).upper()

                if object_type == "DIRECTORY":

                    pending.append(
                        obj.path
                    )

        return result

    # -----------------------------------------------------------------
    # Notebook export
    # -----------------------------------------------------------------

    def export_source(
        self,
        path: str,
    ) -> str:
        """
        Export a notebook in SOURCE format.
        """

        # Native SDK path
        if self._sdk_client is not None:

            return self._sdk_export_source(
                path
            )

        # REST API path
        query = {
            "path": path,
            "format": "SOURCE",
        }

        payload = self._request(
            "GET",
            "/api/2.0/workspace/export",
            query,
        )

        content = payload.get(
            "content"
        )

        if not content:

            raise RepositoryError(
                "Databricks export returned no content "
                f"for '{path}'"
            )

        try:

            return base64.b64decode(
                content
            ).decode(
                "utf-8"
            )

        except (
            ValueError,
            UnicodeDecodeError,
        ) as exc:

            raise RepositoryError(
                "Could not decode exported notebook "
                f"'{path}' from Databricks"
            ) from exc

    # -----------------------------------------------------------------
    # Native SDK notebook export
    # -----------------------------------------------------------------

    def _sdk_export_source(
        self,
        path: str,
    ) -> str:
        """
        Export notebook source using the native Databricks SDK.
        """

        try:

            from databricks.sdk.service.workspace import (
                ExportFormat,
            )

            response = self._sdk_client.workspace.export(
                path=path,
                format=ExportFormat.SOURCE,
            )

            content = getattr(
                response,
                "content",
                None,
            )

            if not content:

                raise RepositoryError(
                    "Databricks SDK export returned no content "
                    f"for '{path}'"
                )

            # Workspace export normally returns base64 encoded
            # notebook content.

            try:

                return base64.b64decode(
                    content
                ).decode(
                    "utf-8"
                )

            except Exception:

                # Fallback for environments where the SDK already
                # exposes decoded content.

                if isinstance(
                    content,
                    bytes,
                ):

                    return content.decode(
                        "utf-8"
                    )

                return str(
                    content
                )

        except RepositoryError:

            raise

        except Exception as exc:

            raise RepositoryError(
                "Databricks SDK notebook export failed "
                f"for '{path}': {exc}"
            ) from exc

    # -----------------------------------------------------------------
    # REST API request
    # -----------------------------------------------------------------

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Dict[str, str],
    ) -> Dict:

        query = urllib.parse.urlencode(
            params
        )

        url = (
            f"{self._base_url}"
            f"{endpoint}"
            f"?{query}"
        )

        request = urllib.request.Request(
            url,
            method=method,
            headers={
                "Authorization": (
                    f"Bearer {self._access_token}"
                ),
                "Accept": "application/json",
            },
        )

        try:

            with urllib.request.urlopen(
                request,
                timeout=self._timeout,
            ) as response:

                raw = response.read().decode(
                    "utf-8"
                )

        except urllib.error.HTTPError as exc:

            body = exc.read().decode(
                "utf-8",
                errors="ignore",
            )

            raise RepositoryError(
                "Databricks API request failed "
                f"({exc.code}) for {endpoint}: "
                f"{body[:500]}"
            ) from exc

        except (
            urllib.error.URLError,
            TimeoutError,
        ) as exc:

            raise RepositoryError(
                "Could not reach Databricks workspace at "
                f"{self._base_url}: {exc}"
            ) from exc

        try:

            return (
                json.loads(raw)
                if raw
                else {}
            )

        except json.JSONDecodeError as exc:

            raise RepositoryError(
                "Databricks API returned invalid JSON "
                f"for {endpoint}"
            ) from exc