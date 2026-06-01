"""
Headless Kubernetes client for Nebius MK8S clusters.

Authentication uses a service account credentials file (sa-credentials.json)
obtained via:
    nebius iam auth-public-key generate --service-account-id $SA_ID --output sa-credentials.json

The SA needs:
  - resource.mk8scluster.get  (to read cluster endpoint + CA via Nebius API)
  - Kubernetes RBAC role      (to call the Kubernetes API itself)

Nebius API endpoints follow the pattern: <service>.api.nebius.cloud:443
The global domain api.nebius.cloud works for all regions — no region-specific domain needed.
"""

import tempfile
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from nebius.sdk import SDK
from nebius.api.nebius.mk8s.v1 import ClusterServiceClient, GetClusterRequest

import kubernetes.client as k8s_client


_TOKEN_REFRESH_MARGIN = timedelta(minutes=5)
_DEFAULT_NEBIUS_DOMAIN = "api.nebius.cloud"


class NebiusK8sClient:
    """
    Provides a kubernetes.client.ApiClient authenticated against a Nebius MK8S cluster.

    Usage:
        with NebiusK8sClient(
            cluster_id="mk8scluster-e00xxxxx",
            credentials_file="sa-credentials.json",
        ) as k8s:
            batch = kubernetes.client.BatchV1Api(k8s.api_client())

    nebius_domain defaults to api.nebius.cloud (global, works for all regions).
    Set use_private_endpoint=True when running from inside the cluster's VPC.
    """

    def __init__(
        self,
        cluster_id: str,
        credentials_file: str | Path,
        nebius_domain: str = _DEFAULT_NEBIUS_DOMAIN,
        use_private_endpoint: bool = False,
    ) -> None:
        self._sdk = SDK(
            credentials_file_name=credentials_file,
            domain=nebius_domain,
        )

        self._token = self._sdk.get_token_sync(timeout=30)

        cluster = self._sdk.run_sync(
            ClusterServiceClient(self._sdk).get(GetClusterRequest(id=cluster_id)),
        )
        cp = cluster.status.control_plane

        if use_private_endpoint:
            endpoint = cp.endpoints.private_endpoint
        else:
            endpoint = cp.endpoints.public_endpoint
            if not endpoint:
                raise ValueError(
                    f"Cluster {cluster_id} has no public endpoint. "
                    "Enable it in the Nebius console, or use use_private_endpoint=True "
                    "when running from inside the cluster VPC."
                )

        ca_pem = cp.auth.cluster_ca_certificate

        self._ca_file = tempfile.NamedTemporaryFile(suffix=".crt", delete=False)
        self._ca_file.write(ca_pem.encode())
        self._ca_file.flush()

        self._config = k8s_client.Configuration()
        self._config.host = endpoint if endpoint.startswith("https://") else f"https://{endpoint}"
        self._config.ssl_ca_cert = self._ca_file.name

    def _bearer_header(self) -> str:
        return f"Bearer {self._token.token}"

    def api_client(self) -> k8s_client.ApiClient:
        """Return a ready ApiClient, refreshing the IAM token if near expiry."""
        if self._token.expiration is not None:
            remaining = self._token.expiration - datetime.now(timezone.utc)
            if remaining < _TOKEN_REFRESH_MARGIN:
                self._token = self._sdk.get_token_sync(timeout=30)
        api = k8s_client.ApiClient(self._config)
        api.set_default_header("Authorization", self._bearer_header())
        return api

    def close(self) -> None:
        """Release SDK resources and remove the temporary CA cert file."""
        self._sdk.sync_close()
        self._ca_file.close()
        os.unlink(self._ca_file.name)

    def __enter__(self) -> "NebiusK8sClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()
