# Running Kubernetes Jobs on Nebius MK8S Using Python

This guide shows you how to submit and manage Kubernetes Jobs on a Nebius MK8S cluster entirely from Python — no `kubectl`, no kubeconfig file, no manual token commands. All you need is a service account credentials file and your cluster ID.

---

## Prerequisites

- Python 3.11+
- A running Nebius MK8S cluster with a **public endpoint** enabled

Install the two Python dependencies:

```bash
pip install nebius kubernetes
```

Download the two files you'll need:

- `nebius_mk8s_client.py` — the authentication library
- `example_job.py` — the example Job script

---

## Step 1 — Create a Service Account

Your Python code will authenticate as a **service account (SA)** — a non-human identity in Nebius IAM. Create one in the same project as your cluster:

```bash
SA_ID=$(nebius iam service-account create \
  --name my-k8s-automation-sa \
  --parent-id <your-project-id> \
  --format json | jq -r '.metadata.id')

echo "Service Account ID: $SA_ID"
```

Alternatively, create it in the Nebius console under **Administration → IAM → Service accounts**.

---

## Step 2 — Grant Permissions

The SA needs permission:

**Nebius IAM permission — to look up the cluster:**

Grant `editor` on your tenant or project via the Nebius console IAM section. This allows the code to automatically retrieve the cluster's API endpoint and CA certificate by cluster ID.

---

## Step 3 — Generate the Credentials File

Run this command once to generate a credentials file for the SA. It creates an RSA key pair, uploads the public key to Nebius IAM, and saves the private key locally:

```bash
nebius iam auth-public-key generate \
  --service-account-id $SA_ID \
  --output ./sa-credentials.json
```

The resulting `sa-credentials.json` is everything your Python code needs to authenticate. Keep it safe — treat it like a password.

> **Important:** Never commit this file to source control. Store it in a secrets manager or a CI/CD secret store.

This is a **one-time step**. The same file works indefinitely until you rotate the key.

---

## Step 4 — Set Environment Variables

The scripts read configuration from environment variables:

```bash
export NEBIUS_CLUSTER_ID=mk8scluster-e00xxxxx
export NEBIUS_CREDENTIALS_FILE=/path/to/sa-credentials.json
```

Find your cluster ID in the Nebius console under **MK8S → Clusters**, or with:

```bash
nebius mk8s v1 cluster list --parent-id <your-project-id>
```

---

## Step 5 — Run the Example Job

```bash
python3 example_job.py
```

You should see:

```
Submitting job 'example-job'...
Waiting for completion...
Job succeeded.

--- logs from example-job-j7qzs ---
Hello from Nebius MK8S

Cleaning up job 'example-job'...
```

The script submits a Job, waits for it to finish, prints its logs, and deletes it — all from Python.

---

## Using the Library in Your Own Code

`nebius_mk8s_client.py` provides a single class — `NebiusK8sClient` — that handles authentication and returns a standard `kubernetes.ApiClient`. Use it as a context manager:

```python
from nebius_mk8s_client import NebiusK8sClient
import kubernetes.client as k8s_client

with NebiusK8sClient(
    cluster_id="mk8scluster-e00xxxxx",
    credentials_file="/path/to/sa-credentials.json",
) as k8s:
    api = k8s.api_client()

    # Submit a Job
    batch = k8s_client.BatchV1Api(api)
    batch.create_namespaced_job(namespace="default", body=your_job_manifest)

    # List pods
    core = k8s_client.CoreV1Api(api)
    pods = core.list_namespaced_pod(namespace="default")
```

Once you have an `ApiClient`, you can use any standard Kubernetes Python client operation — the library handles everything else: token acquisition, CA certificate setup, and automatic token refresh.

### Running from inside the cluster VPC

If your code runs on a Nebius VM or pod within the same VPC as the cluster, use the private endpoint instead:

```python
with NebiusK8sClient(
    cluster_id="mk8scluster-e00xxxxx",
    credentials_file="/path/to/sa-credentials.json",
    use_private_endpoint=True,
) as k8s:
    ...
```

Or set the environment variable:

```bash
export NEBIUS_USE_PRIVATE_ENDPOINT=true
```

---

## Rotating the Credentials

When you need to rotate the SA key, re-run the generation command and update the secret:

```bash
nebius iam auth-public-key generate \
  --service-account-id $SA_ID \
  --output ./sa-credentials.json
```

The old key stays valid in Nebius IAM until you explicitly delete it, giving you a zero-downtime rotation window to update your secret and redeploy.

---

## Summary

| What you need | Where it comes from |
|---|---|
| `sa-credentials.json` | `nebius iam auth-public-key generate` (one-time) |
| `NEBIUS_CLUSTER_ID` | Nebius console or `nebius mk8s v1 cluster list` |
| `nebius` + `kubernetes` packages | `pip install nebius kubernetes` |

Once those three are in place, your Python code can create, monitor, and delete Kubernetes Jobs on any Nebius MK8S cluster — from a local script, a CI/CD pipeline, or a pod running inside the cluster itself.
