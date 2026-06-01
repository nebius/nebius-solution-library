"""
Example: submit a Kubernetes Job to a Nebius MK8S cluster and stream its logs.

Required environment variables:
    NEBIUS_CLUSTER_ID       - MK8S cluster ID, e.g. mk8scluster-e00xxxxx
    NEBIUS_CREDENTIALS_FILE - Path to sa-credentials.json

Optional:
    NEBIUS_USE_PRIVATE_ENDPOINT - set to "true" when running inside the cluster VPC
"""

import os
import sys
import time
import kubernetes.client as k8s_client
from nebius_mk8s_client import NebiusK8sClient


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"Error: environment variable {name} is not set.", file=sys.stderr)
        sys.exit(1)
    return value


CLUSTER_ID = _require_env("NEBIUS_CLUSTER_ID")
CREDENTIALS_FILE = _require_env("NEBIUS_CREDENTIALS_FILE")
USE_PRIVATE_ENDPOINT = os.environ.get("NEBIUS_USE_PRIVATE_ENDPOINT", "").lower() == "true"

JOB_NAME = "example-job"
NAMESPACE = "default"

def make_job_manifest() -> k8s_client.V1Job:
    return k8s_client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=k8s_client.V1ObjectMeta(name=JOB_NAME),
        spec=k8s_client.V1JobSpec(
            template=k8s_client.V1PodTemplateSpec(
                spec=k8s_client.V1PodSpec(
                    restart_policy="Never",
                    containers=[
                        k8s_client.V1Container(
                            name="example",
                            image="busybox",
                            command=["sh", "-c", "echo Hello from Nebius MK8S && sleep 5"],
                        )
                    ],
                )
            ),
            backoff_limit=0,
        ),
    )


def wait_for_job(batch: k8s_client.BatchV1Api, name: str, namespace: str, timeout: int = 120) -> str:
    """Poll until the job reaches a terminal state. Returns 'succeeded' or 'failed'."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = batch.read_namespaced_job(name=name, namespace=namespace)
        if job.status.succeeded:
            return "succeeded"
        if job.status.failed:
            return "failed"
        time.sleep(5)
    return "timeout"


def stream_pod_logs(core: k8s_client.CoreV1Api, job_name: str, namespace: str) -> None:
    pods = core.list_namespaced_pod(
        namespace=namespace,
        label_selector=f"job-name={job_name}",
    )
    for pod in pods.items:
        print(f"\n--- logs from {pod.metadata.name} ---")
        logs = core.read_namespaced_pod_log(name=pod.metadata.name, namespace=namespace)
        print(logs)


def main() -> None:
    with NebiusK8sClient(
        cluster_id=CLUSTER_ID,
        credentials_file=CREDENTIALS_FILE,
        use_private_endpoint=USE_PRIVATE_ENDPOINT,
    ) as k8s:
        api = k8s.api_client()
        batch = k8s_client.BatchV1Api(api)
        core = k8s_client.CoreV1Api(api)

        print(f"Submitting job '{JOB_NAME}'...")
        batch.create_namespaced_job(namespace=NAMESPACE, body=make_job_manifest())

        print("Waiting for completion...")
        result = wait_for_job(batch, JOB_NAME, NAMESPACE)
        print(f"Job {result}.")

        stream_pod_logs(core, JOB_NAME, NAMESPACE)

        print(f"\nCleaning up job '{JOB_NAME}'...")
        batch.delete_namespaced_job(
            name=JOB_NAME,
            namespace=NAMESPACE,
            body=k8s_client.V1DeleteOptions(propagation_policy="Foreground"),
        )


if __name__ == "__main__":
    main()
