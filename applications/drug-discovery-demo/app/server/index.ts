/**
 * Pipeline Server
 *
 * Lightweight Express server for pipeline CRUD and execution.
 * In development, Vite proxies /api/pipelines/* to this server.
 * In production, this server can also serve the built frontend.
 */

import express from 'express';
import cors from 'cors';
import { existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { nimProxyRouter } from './routes/nimProxy.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = parseInt(process.env.PORT || '3001', 10);

const app = express();

// Middleware
app.use(cors());
app.use(express.json({ limit: '10mb' }));

// API routes
app.use('/api/nim-proxy', nimProxyRouter);

// Health check
app.get('/api/health', (_req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// In production, serve the built frontend
const distDir = join(__dirname, '..', 'dist');
if (existsSync(distDir)) {
  app.use(express.static(distDir));

  // SPA fallback - serve index.html for all non-API routes
  app.get('{*path}', (_req, res) => {
    res.sendFile(join(distDir, 'index.html'));
  });
}

app.listen(PORT, () => {
  console.log(`Pipeline server running on http://localhost:${PORT}`);
  console.log(`  API: http://localhost:${PORT}/api/pipelines`);
  if (existsSync(distDir)) {
    console.log(`  Frontend: http://localhost:${PORT}`);
  }
});
