/**
 * NIM API Service
 *
 * Core utilities for interacting with NVIDIA NIM endpoints.
 * This module provides:
 * - URL building (with dev/prod proxy handling)
 * - Health checking
 * - Streaming chat for LLM
 *
 * ## Endpoint Registry
 *
 * All endpoints are defined in `data/endpoints.ts`. This module provides
 * a centralized way to build URLs for any endpoint.
 *
 * ## Proxy Handling
 *
 * In development, requests go through Vite's proxy to avoid CORS:
 * `/api/nim-proxy/{host}/{port}{path}`
 *
 * In production, requests go directly to NIM endpoints:
 * `http://{host}:{port}{path}`
 */

import type { NimEndpoint } from '../data/endpoints';

/**
 * Centralized endpoint configuration
 *
 * Maps endpoint IDs to their port and path. This is the single source of truth
 * for endpoint URLs, used by both service functions and the agent's execute_raw_request.
 */
export const ENDPOINT_CONFIG: Record<string, { port: number; path: string }> = {
  // LLM
  qwen3: { port: 8008, path: '/v1/chat/completions' },

  // Structure Prediction
  openfold3: { port: 8000, path: '/biology/openfold/openfold3/predict' },
  boltz2: { port: 8001, path: '/biology/mit/boltz2/predict' },
  openfold2: { port: 8004, path: '/biology/openfold/openfold2/predict-structure-from-msa-and-template' },

  // Molecule Generation
  genmol: { port: 8005, path: '/biology/nvidia/genmol/generate' },
  molmim: { port: 8006, path: '/generate' },

  // Docking
  diffdock: { port: 8007, path: '/molecular-docking/diffdock/generate' },

  // Utilities
  'msa-search': { port: 8003, path: '/biology/colabfold/msa-search/predict' },
  evo2: { port: 8002, path: '/biology/arc/evo2/generate' },

  // Protein Design
  proteinmpnn: { port: 8009, path: '/biology/ipd/proteinmpnn/predict' },
  rfdiffusion: { port: 8010, path: '/biology/ipd/rfdiffusion/generate' },
} as const;

export type EndpointId = keyof typeof ENDPOINT_CONFIG;

/**
 * Get endpoint configuration by ID
 */
export function getEndpointConfig(endpointId: string): { port: number; path: string } | undefined {
  return ENDPOINT_CONFIG[endpointId.toLowerCase()];
}

/**
 * Build URL for a known endpoint by ID
 */
export function buildEndpointUrl(gatewayUrl: string, endpointId: EndpointId): string {
  const config = ENDPOINT_CONFIG[endpointId];
  if (!config) {
    throw new Error(`Unknown endpoint: ${endpointId}`);
  }
  return buildNimUrl(gatewayUrl, config.port, config.path);
}

export interface HealthCheckResult {
  id: string;
  status: 'ready' | 'not-ready';
  error?: string;
}

/**
 * Normalize a gateway URL (remove protocol, trailing slashes)
 */
export function normalizeGatewayUrl(url: string): string {
  let normalized = url.trim();
  normalized = normalized.replace(/^https?:\/\//, '');
  normalized = normalized.replace(/\/$/, '');
  return normalized;
}

/**
 * Build URL for NIM endpoint.
 * In development, uses the Vite proxy to avoid CORS.
 * In production, uses the Express server's NIM proxy (/api/nim-proxy/)
 * so the browser only needs to reach the Express server, not each NIM directly.
 * This is critical for K8s deployments where NIMs are cluster-internal.
 */
export function buildNimUrl(
  gatewayUrl: string,
  port: number,
  path: string
): string {
  const baseUrl = normalizeGatewayUrl(gatewayUrl);

  // Both dev and prod use the proxy route.
  // In dev: Vite intercepts /api/nim-proxy/* and proxies to the NIM.
  // In prod: Express server intercepts /api/nim-proxy/* and proxies to the NIM.
  // The server can override the host via NIM_GATEWAY_URL env var for cluster-internal routing.
  return `/api/nim-proxy/${baseUrl}/${port}${path}`;
}

/**
 * Check health of a single NIM endpoint
 */
export async function checkEndpointHealth(
  gatewayUrl: string,
  endpoint: NimEndpoint,
  timeoutMs: number = 5000
): Promise<HealthCheckResult> {
  const healthUrl = buildNimUrl(gatewayUrl, endpoint.port, endpoint.healthPath);

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    const response = await fetch(healthUrl, {
      method: 'GET',
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    return {
      id: endpoint.id,
      status: response.ok ? 'ready' : 'not-ready',
    };
  } catch (error) {
    const errorMessage =
      error instanceof Error ? error.message : 'Unknown error';
    return {
      id: endpoint.id,
      status: 'not-ready',
      error: errorMessage,
    };
  }
}

/**
 * Check health of all NIM endpoints in parallel
 */
export async function checkAllEndpointsHealth(
  gatewayUrl: string,
  endpoints: NimEndpoint[],
  timeoutMs: number = 5000
): Promise<HealthCheckResult[]> {
  const healthChecks = endpoints.map((endpoint) =>
    checkEndpointHealth(gatewayUrl, endpoint, timeoutMs)
  );

  return Promise.all(healthChecks);
}

/**
 * Chat message interface
 */
export interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

/**
 * Call the Qwen3 LLM with streaming support
 * Returns an async generator that yields content chunks
 */
export async function* streamChat(
  gatewayUrl: string,
  messages: ChatMessage[],
  options: {
    model?: string;
    temperature?: number;
    maxTokens?: number;
  } = {}
): AsyncGenerator<string, void, unknown> {
  const { model = 'Qwen/Qwen3-Next-80B-A3B-Instruct', temperature = 0, maxTokens = 2048 } = options;

  const chatUrl = buildNimUrl(gatewayUrl, 8008, '/v1/chat/completions');

  const response = await fetch(chatUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model,
      messages,
      temperature,
      max_tokens: maxTokens,
      stream: true,
    }),
  });

  if (!response.ok) {
    throw new Error(`Chat request failed: ${response.status} ${response.statusText}`);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('No response body');
  }

  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // Process complete SSE lines
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || trimmed === 'data: [DONE]') continue;

        if (trimmed.startsWith('data: ')) {
          try {
            const json = JSON.parse(trimmed.slice(6));
            const content = json.choices?.[0]?.delta?.content;
            if (content) {
              yield content;
            }
          } catch {
            // Skip malformed JSON
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/**
 * Non-streaming chat call (for simpler use cases)
 */
export async function chat(
  gatewayUrl: string,
  messages: ChatMessage[],
  options: {
    model?: string;
    temperature?: number;
    maxTokens?: number;
  } = {}
): Promise<string> {
  const { model = 'Qwen/Qwen3-Next-80B-A3B-Instruct', temperature = 0, maxTokens = 2048 } = options;

  const chatUrl = buildNimUrl(gatewayUrl, 8008, '/v1/chat/completions');

  const response = await fetch(chatUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model,
      messages,
      temperature,
      max_tokens: maxTokens,
      stream: false,
    }),
  });

  if (!response.ok) {
    throw new Error(`Chat request failed: ${response.status} ${response.statusText}`);
  }

  const data = await response.json();
  return data.choices?.[0]?.message?.content || '';
}
