/**
 * Vite Plugin for kubectl Proxy
 * Provides REST API endpoints to interact with Kubernetes cluster via kubectl CLI
 */

import { spawn } from 'child_process';
import type { Plugin } from 'vite';
import type { IncomingMessage, ServerResponse } from 'http';

interface KubectlResult {
  success: boolean;
  data?: unknown;
  error?: string;
}

/**
 * Execute kubectl command and return parsed JSON result
 */
function execKubectl(args: string[]): Promise<KubectlResult> {
  return new Promise((resolve) => {
    const proc = spawn('kubectl', args, {
      env: { ...process.env },
    });

    let stdout = '';
    let stderr = '';

    proc.stdout.on('data', (data) => {
      stdout += data.toString();
    });

    proc.stderr.on('data', (data) => {
      stderr += data.toString();
    });

    proc.on('error', (err) => {
      resolve({ success: false, error: `Failed to spawn kubectl: ${err.message}` });
    });

    proc.on('close', (code) => {
      if (code === 0) {
        try {
          // Try to parse as JSON if possible
          const data = stdout.trim();
          if (data.startsWith('{') || data.startsWith('[')) {
            resolve({ success: true, data: JSON.parse(data) });
          } else {
            resolve({ success: true, data: data });
          }
        } catch {
          resolve({ success: true, data: stdout.trim() });
        }
      } else {
        resolve({ success: false, error: stderr || `kubectl exited with code ${code}` });
      }
    });
  });
}

/**
 * Parse request body as JSON
 */
function parseBody(req: IncomingMessage): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', (chunk) => {
      body += chunk.toString();
    });
    req.on('end', () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch (err) {
        reject(err);
      }
    });
    req.on('error', reject);
  });
}

/**
 * Send JSON response
 */
function sendJson(res: ServerResponse, data: unknown, status = 200) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json');
  res.end(JSON.stringify(data));
}

/**
 * Extract query params from URL
 */
function getQueryParams(url: string): URLSearchParams {
  const urlObj = new URL(url, 'http://localhost');
  return urlObj.searchParams;
}

export function kubectlPlugin(): Plugin {
  return {
    name: 'vite-plugin-kubectl',
    configureServer(server) {
      // Single middleware that routes all /api/k8s/* requests
      server.middlewares.use(async (req, res, next) => {
        const url = req.url || '';

        // Only handle /api/k8s/* routes
        if (!url.startsWith('/api/k8s/')) {
          return next();
        }

        try {
          // Health check - verify kubectl is available and connected
          if (url.startsWith('/api/k8s/health') && req.method === 'GET') {
            const result = await execKubectl(['config', 'current-context']);
            if (result.success) {
              sendJson(res, {
                connected: true,
                context: result.data,
              });
            } else {
              sendJson(res, {
                connected: false,
                error: result.error,
              }, 503);
            }
            return;
          }

          // Get all deployments in namespace
          if (url.startsWith('/api/k8s/deployments') && req.method === 'GET') {
            const params = getQueryParams(url);
            const namespace = params.get('namespace') || 'default';
            const result = await execKubectl([
              'get', 'deployments',
              '-n', namespace,
              '-o', 'json',
            ]);

            if (result.success) {
              sendJson(res, result.data);
            } else {
              sendJson(res, { error: result.error }, 500);
            }
            return;
          }

          // Get pods for a specific deployment
          if (url.startsWith('/api/k8s/pods') && req.method === 'GET') {
            const params = getQueryParams(url);
            const namespace = params.get('namespace') || 'default';
            const deployment = params.get('deployment');

            const args = ['get', 'pods', '-n', namespace, '-o', 'json'];
            if (deployment) {
              args.push('-l', `app=${deployment}`);
            }

            const result = await execKubectl(args);
            if (result.success) {
              sendJson(res, result.data);
            } else {
              sendJson(res, { error: result.error }, 500);
            }
            return;
          }

          // Scale a deployment (use exact path match to avoid matching scale-nodegroup)
          if ((url === '/api/k8s/scale' || url.startsWith('/api/k8s/scale?')) && req.method === 'POST') {
            const body = await parseBody(req);
            const { deployment, replicas, namespace = 'default' } = body as {
              deployment: string;
              replicas: number;
              namespace?: string;
            };

            if (!deployment || replicas === undefined) {
              sendJson(res, { error: 'Missing deployment or replicas' }, 400);
              return;
            }

            const result = await execKubectl([
              'scale', 'deployment', deployment,
              '--replicas', String(replicas),
              '-n', String(namespace),
            ]);

            if (result.success) {
              sendJson(res, { success: true, message: result.data });
            } else {
              sendJson(res, { error: result.error }, 500);
            }
            return;
          }

          // Get nodes with GPU info
          if (url.startsWith('/api/k8s/nodes') && req.method === 'GET') {
            const result = await execKubectl([
              'get', 'nodes',
              '-o', 'json',
            ]);

            if (result.success) {
              sendJson(res, result.data);
            } else {
              sendJson(res, { error: result.error }, 500);
            }
            return;
          }

          // Get cluster resource quota/capacity
          if (url.startsWith('/api/k8s/capacity') && req.method === 'GET') {
            // Get nodes and their allocatable resources
            const nodesResult = await execKubectl([
              'get', 'nodes',
              '-o', 'jsonpath={range .items[*]}{.metadata.name}|{.status.allocatable}|{.metadata.labels}\\n{end}',
            ]);

            // Get current pod resource usage
            const podsResult = await execKubectl([
              'get', 'pods', '--all-namespaces',
              '-o', 'jsonpath={range .items[*]}{.spec.nodeName}|{.spec.containers[*].resources.requests}\\n{end}',
            ]);

            if (nodesResult.success) {
              sendJson(res, {
                nodes: nodesResult.data,
                pods: podsResult.success ? podsResult.data : null,
              });
            } else {
              sendJson(res, { error: nodesResult.error }, 500);
            }
            return;
          }

          // Get HPA (Horizontal Pod Autoscaler) status
          if (url.startsWith('/api/k8s/hpa') && req.method === 'GET') {
            const params = getQueryParams(url);
            const namespace = params.get('namespace') || 'default';
            const result = await execKubectl([
              'get', 'hpa',
              '-n', namespace,
              '-o', 'json',
            ]);

            if (result.success) {
              sendJson(res, result.data);
            } else {
              // HPA might not exist, return empty list
              sendJson(res, { items: [] });
            }
            return;
          }

          // Get node groups/pools info
          if (url.startsWith('/api/k8s/nodegroups') && req.method === 'GET') {
            // Try to get node groups from various sources:
            // 1. Cluster-API MachineDeployments
            // 2. Node labels that indicate node group membership

            // First, try MachineDeployments (cluster-api)
            const machineDeploymentsResult = await execKubectl([
              'get', 'machinedeployments',
              '--all-namespaces',
              '-o', 'json',
            ]);

            if (machineDeploymentsResult.success && machineDeploymentsResult.data) {
              sendJson(res, {
                type: 'machinedeployments',
                data: machineDeploymentsResult.data,
              });
              return;
            }

            // Fallback: Get unique node groups from node labels
            const nodesResult = await execKubectl([
              'get', 'nodes',
              '-o', 'json',
            ]);

            if (nodesResult.success && nodesResult.data) {
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              const nodes = nodesResult.data as any;
              const nodeGroups: Record<string, { count: number; gpuType: string; gpuPerNode: number }> = {};

              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              for (const node of nodes.items || []) {
                const labels = node.metadata?.labels || {};
                // Try common node group labels
                const nodeGroupName = labels['node.kubernetes.io/instance-type'] ||
                                      labels['nebius.ai/node-group'] ||
                                      labels['cloud.google.com/gke-nodepool'] ||
                                      labels['eks.amazonaws.com/nodegroup'] ||
                                      labels['agentpool'] ||
                                      'default';

                const gpuType = labels['nvidia.com/gpu.product'] || labels['nvidia.com/gpu-product'] || 'unknown';
                const gpuCount = parseInt(node.status?.allocatable?.['nvidia.com/gpu'] || '0', 10);

                if (!nodeGroups[nodeGroupName]) {
                  nodeGroups[nodeGroupName] = { count: 0, gpuType, gpuPerNode: gpuCount };
                }
                nodeGroups[nodeGroupName].count += 1;
              }

              sendJson(res, {
                type: 'labels',
                nodeGroups,
              });
              return;
            }

            sendJson(res, { error: 'Could not determine node groups' }, 500);
            return;
          }

          // Scale node group (via Nebius CLI or cluster-api)
          if (url.startsWith('/api/k8s/scale-nodegroup') && req.method === 'POST') {
            const body = await parseBody(req);
            const { nodeGroupId, nodeCount } = body as {
              nodeGroupId: string;
              nodeCount: number;
            };

            if (!nodeGroupId || nodeCount === undefined) {
              sendJson(res, { error: 'Missing nodeGroupId or nodeCount' }, 400);
              return;
            }

            // Try using nebius CLI (if available)
            const result = await new Promise<KubectlResult & { cliAvailable?: boolean }>((resolve) => {
              const proc = spawn('nebius', [
                'mk8s', 'node-group', 'update',
                '--id', nodeGroupId,
                '--fixed-node-count', String(nodeCount),
              ], { env: { ...process.env } });

              let stdout = '';
              let stderr = '';

              proc.stdout.on('data', (data) => { stdout += data.toString(); });
              proc.stderr.on('data', (data) => { stderr += data.toString(); });

              proc.on('error', () => {
                // Nebius CLI not available, try cluster-api
                resolve({ success: false, error: 'Nebius CLI not available', cliAvailable: false });
              });

              proc.on('close', (code) => {
                if (code === 0) {
                  resolve({ success: true, data: stdout.trim(), cliAvailable: true });
                } else {
                  resolve({ success: false, error: stderr || `nebius exited with code ${code}`, cliAvailable: true });
                }
              });
            });

            if (result.success) {
              sendJson(res, { success: true, message: result.data });
              return;
            }

            // If Nebius CLI is available but returned an error, report the API error directly
            if (result.cliAvailable) {
              // Extract trace ID if present in error
              const traceMatch = result.error?.match(/request\s*=\s*([a-f0-9-]+)/i);
              const traceId = traceMatch ? traceMatch[1] : null;

              sendJson(res, {
                success: false,
                error: `Nebius API error: ${result.error}`,
                traceId: traceId,
                suggestion: 'This may be a temporary issue with the Nebius API. Try again in a few moments, or contact Nebius support with the trace ID.',
              }, 500);
              return;
            }

            // Fallback: Try cluster-api MachineDeployment scaling
            const mdResult = await execKubectl([
              'scale', 'machinedeployment', nodeGroupId,
              '--replicas', String(nodeCount),
              '--all-namespaces',
            ]);

            if (mdResult.success) {
              sendJson(res, { success: true, message: mdResult.data });
            } else {
              sendJson(res, {
                success: false,
                error: 'Node group scaling not available. Install Nebius CLI or use Cluster API.',
                nebiusError: result.error,
                clusterApiError: mdResult.error,
              }, 500);
            }
            return;
          }

          // Unknown route
          sendJson(res, { error: 'Unknown k8s API route' }, 404);
        } catch (err) {
          console.error('[kubectl-plugin] Error:', err);
          sendJson(res, { error: 'Internal server error' }, 500);
        }
      });

      console.log('[kubectl-plugin] K8s API proxy registered at /api/k8s/*');
    },
  };
}
