// NIM API service for health checks and API calls

import type { NimEndpoint } from '../data/endpoints';

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
 * In development, uses local proxy to avoid CORS.
 * In production, hits the NIM endpoints directly.
 */
export function buildNimUrl(
  gatewayUrl: string,
  port: number,
  path: string
): string {
  const baseUrl = normalizeGatewayUrl(gatewayUrl);

  // In development, use the Vite proxy to avoid CORS
  if (import.meta.env.DEV) {
    return `/api/nim-proxy/${baseUrl}/${port}${path}`;
  }

  // In production, hit the endpoints directly
  return `http://${baseUrl}:${port}${path}`;
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
