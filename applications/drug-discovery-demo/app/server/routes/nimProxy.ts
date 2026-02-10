/**
 * NIM Proxy Route
 *
 * Proxies requests to NIM services. In production (K8s), the NIM services
 * are only accessible internally - this proxy bridges the browser to them.
 *
 * Route: /api/nim-proxy/:host/:port/{*path}
 *
 * The host can be:
 * - An external IP (e.g., 46.243.144.128)
 * - A K8s service name (e.g., boltz2.nims.svc.cluster.local)
 * - Set via NIM_GATEWAY_URL env var for cluster-internal routing
 */

import { Router, type Request, type Response } from 'express';
import http from 'node:http';

export const nimProxyRouter = Router();

// If NIM_GATEWAY_URL is set, override the host in all proxy requests.
// This lets the frontend use any gateway URL but the server routes
// to the correct internal address.
const GATEWAY_OVERRIDE = process.env.NIM_GATEWAY_URL || '';

nimProxyRouter.all('/:host/:port/{*path}', (req: Request, res: Response) => {
  const host = GATEWAY_OVERRIDE || req.params.host;
  const port = parseInt(req.params.port, 10);
  // Express 5 / path-to-regexp v8: {*path} returns an array of segments
  const rawPath = req.params.path;
  const targetPath = '/' + (Array.isArray(rawPath) ? rawPath.join('/') : (rawPath || ''));
  const method = req.method;

  // Timeout: 5 minutes for POST (structure prediction), 30s for GET
  const timeout = method === 'POST' ? 300_000 : 30_000;

  console.log(`[NIM Proxy] ${method} http://${host}:${port}${targetPath}`);

  if (method === 'POST') {
    const body = JSON.stringify(req.body);

    // Check if streaming
    let isStreaming = false;
    try {
      isStreaming = req.body?.stream === true;
    } catch { /* ignore */ }

    const proxyReq = http.request(
      {
        hostname: host,
        port,
        path: targetPath,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(body),
          'Accept': isStreaming ? 'text/event-stream' : 'application/json',
        },
        timeout,
      },
      (proxyRes) => {
        if (isStreaming) {
          res.writeHead(proxyRes.statusCode || 500, {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
          });
          proxyRes.pipe(res);
        } else {
          let responseBody = '';
          proxyRes.on('data', (chunk: Buffer) => {
            responseBody += chunk.toString();
          });
          proxyRes.on('end', () => {
            res.writeHead(proxyRes.statusCode || 500, {
              'Content-Type': 'application/json',
            });
            res.end(responseBody);
          });
        }
      },
    );

    proxyReq.on('error', (err) => {
      console.error(`[NIM Proxy] Error: ${err.message}`);
      if (!res.headersSent) {
        res.status(502).json({ error: err.message });
      }
    });

    proxyReq.on('timeout', () => {
      proxyReq.destroy();
      if (!res.headersSent) {
        res.status(504).json({ error: 'Gateway timeout' });
      }
    });

    proxyReq.write(body);
    proxyReq.end();
  } else {
    // GET and other methods
    const proxyReq = http.request(
      {
        hostname: host,
        port,
        path: targetPath,
        method,
        timeout,
      },
      (proxyRes) => {
        res.writeHead(proxyRes.statusCode || 500, proxyRes.headers);
        proxyRes.pipe(res);
      },
    );

    proxyReq.on('error', (err) => {
      console.error(`[NIM Proxy] Error: ${err.message}`);
      if (!res.headersSent) {
        res.status(502).json({ error: err.message });
      }
    });

    proxyReq.on('timeout', () => {
      proxyReq.destroy();
      if (!res.headersSent) {
        res.status(504).json({ error: 'Gateway timeout' });
      }
    });

    proxyReq.end();
  }
});
