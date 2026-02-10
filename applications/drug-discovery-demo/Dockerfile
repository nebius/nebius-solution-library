# ============================================================================
# Drug Discovery Demo - Multi-stage Docker Build
#
# Stage 1: Build the React frontend
# Stage 2: Install server dependencies + run Express
# ============================================================================

# --- Build stage ---
FROM node:22-alpine AS build

WORKDIR /build

# Install frontend dependencies
COPY app/package.json app/package-lock.json ./
RUN npm ci

# Copy frontend source and build
COPY app/ ./
RUN npm run build

# --- Production stage ---
FROM node:22-alpine AS production

WORKDIR /app

# Copy server code
COPY app/server/package.json app/server/package-lock.json ./server/
WORKDIR /app/server
RUN npm ci --omit=dev

# Copy server source
COPY app/server/ ./

# Copy built frontend from build stage
COPY --from=build /build/dist /app/dist

WORKDIR /app/server

# Environment variables (override at deployment time)
ENV PORT=3001
ENV NODE_ENV=production
# NIM_GATEWAY_URL - set to cluster-internal gateway IP or leave empty
# to use the gateway URL from the frontend UI

EXPOSE 3001

CMD ["npx", "tsx", "index.ts"]
