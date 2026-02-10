import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import type { Plugin } from 'vite'
import http from 'http'
import { kubectlPlugin } from './vite-plugin-kubectl'

// Custom plugin to proxy NIM requests
function nimProxyPlugin(): Plugin {
  return {
    name: 'nim-proxy',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        // Handle /api/nim-proxy/:host/:port/* requests
        const match = req.url?.match(/^\/api\/nim-proxy\/([^/]+)\/(\d+)(.*)$/);
        if (!match) {
          return next();
        }

        const [, host, portStr, path] = match;
        const port = parseInt(portStr, 10);
        const targetPath = path || '/';

        // Use longer timeout for POST requests (structure prediction can take time)
        const timeout = req.method === 'POST' ? 300000 : 10000;

        console.log(`[NIM Proxy] ${req.method} http://${host}:${port}${targetPath}`);

        // For POST requests, collect the body first to ensure proper forwarding
        if (req.method === 'POST') {
          let body = '';
          req.on('data', (chunk: Buffer) => {
            body += chunk.toString();
          });
          req.on('end', () => {
            console.log(`[NIM Proxy] Request body length: ${body.length}`);
            console.log(`[NIM Proxy] Request body preview: ${body.substring(0, 500)}...`);

            // Check if this is a streaming request (for LLM chat)
            let isStreamingRequest = false;
            try {
              const parsedBody = JSON.parse(body);
              isStreamingRequest = parsedBody.stream === true;
            } catch {
              // Not JSON, continue as normal
            }

            const proxyReq = http.request(
              {
                hostname: host,
                port: port,
                path: targetPath,
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                  'Content-Length': Buffer.byteLength(body),
                  'Accept': isStreamingRequest ? 'text/event-stream' : 'application/json',
                },
                timeout: timeout,
              },
              (proxyRes) => {
                // For streaming responses, pipe directly without buffering
                if (isStreamingRequest) {
                  console.log(`[NIM Proxy] Streaming response started`);
                  res.writeHead(proxyRes.statusCode || 500, {
                    'Content-Type': 'text/event-stream',
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive',
                    'Access-Control-Allow-Origin': '*',
                  });

                  proxyRes.on('data', (chunk: Buffer) => {
                    res.write(chunk);
                  });

                  proxyRes.on('end', () => {
                    console.log(`[NIM Proxy] Streaming response completed`);
                    res.end();
                  });
                } else {
                  // For non-streaming, buffer the response
                  let responseBody = '';
                  proxyRes.on('data', (chunk: Buffer) => {
                    responseBody += chunk.toString();
                  });
                  proxyRes.on('end', () => {
                    console.log(`[NIM Proxy] Response status: ${proxyRes.statusCode}`);
                    if (proxyRes.statusCode !== 200) {
                      console.log(`[NIM Proxy] Response body: ${responseBody.substring(0, 1000)}`);
                    }
                    res.writeHead(proxyRes.statusCode || 500, {
                      'Content-Type': 'application/json',
                      'Access-Control-Allow-Origin': '*',
                    });
                    res.end(responseBody);
                  });
                }
              }
            );

            proxyReq.on('error', (err) => {
              console.error(`[NIM Proxy] Error: ${err.message}`);
              if (!res.headersSent) {
                res.writeHead(502);
                res.end(JSON.stringify({ error: err.message }));
              }
            });

            proxyReq.on('timeout', () => {
              console.error('[NIM Proxy] Timeout');
              proxyReq.destroy();
              if (!res.headersSent) {
                res.writeHead(504);
                res.end(JSON.stringify({ error: 'Gateway timeout' }));
              }
            });

            proxyReq.write(body);
            proxyReq.end();
          });
        } else {
          // For GET requests, use simple piping
          let headersSent = false;

          const proxyReq = http.request(
            {
              hostname: host,
              port: port,
              path: targetPath,
              method: req.method,
              headers: {
                ...req.headers,
                host: `${host}:${port}`,
              },
              timeout: timeout,
            },
            (proxyRes) => {
              headersSent = true;
              res.writeHead(proxyRes.statusCode || 500, proxyRes.headers);
              proxyRes.pipe(res);
            }
          );

          proxyReq.on('error', (err) => {
            console.error(`[NIM Proxy] Error: ${err.message}`);
            if (!headersSent && !res.headersSent) {
              res.writeHead(502);
              res.end(JSON.stringify({ error: err.message }));
            }
          });

          proxyReq.on('timeout', () => {
            console.error('[NIM Proxy] Timeout');
            proxyReq.destroy();
            if (!headersSent && !res.headersSent) {
              res.writeHead(504);
              res.end(JSON.stringify({ error: 'Gateway timeout' }));
            }
          });

          req.pipe(proxyReq);
        }
      });
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), nimProxyPlugin(), kubectlPlugin()],
  server: {},
})
