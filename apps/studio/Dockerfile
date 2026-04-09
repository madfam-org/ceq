# CEQ Studio - Next.js Frontend
#
# Multi-stage build for production deployment with standalone output.
#
# Build:
#   docker build -t ceq-studio:latest .
#
# Run:
#   docker run -p 5801:5801 ceq-studio:latest

# =============================================================================
# Stage 1: Install dependencies
# =============================================================================
FROM node:20-alpine AS deps

WORKDIR /app

# Copy workspace root config + lockfile + all package.json files
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/studio/package.json ./apps/studio/
COPY packages/ui/package.json ./packages/ui/
COPY packages/workflow-types/package.json ./packages/workflow-types/
RUN corepack enable && corepack prepare pnpm@9.14.4 --activate && \
    pnpm install --frozen-lockfile || pnpm install

# =============================================================================
# Stage 2: Build the application
# =============================================================================
FROM node:20-alpine AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/apps/studio/node_modules ./apps/studio/node_modules
COPY --from=deps /app/packages/ ./packages/
COPY apps/studio/ ./apps/studio/

# Build arguments for environment variables (OAuth client registered in Janua 2025-12-10)
ARG NEXT_PUBLIC_API_URL=https://api.ceq.lol
ARG NEXT_PUBLIC_WS_URL=wss://ws.ceq.lol
ARG NEXT_PUBLIC_JANUA_DOMAIN=auth.madfam.io
ARG NEXT_PUBLIC_JANUA_CLIENT_ID=jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk

ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL
ENV NEXT_PUBLIC_JANUA_DOMAIN=$NEXT_PUBLIC_JANUA_DOMAIN
ENV NEXT_PUBLIC_JANUA_CLIENT_ID=$NEXT_PUBLIC_JANUA_CLIENT_ID
ENV NEXT_TELEMETRY_DISABLED=1

WORKDIR /app/apps/studio

# Build Next.js with standalone output
RUN corepack enable && corepack prepare pnpm@9.14.4 --activate && pnpm build

# =============================================================================
# Stage 3: Production image
# =============================================================================
FROM node:20-alpine AS production

WORKDIR /app

# Create non-root user
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy built assets
COPY --from=builder /app/apps/studio/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/apps/studio/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/apps/studio/.next/static ./.next/static

# Environment
ENV NODE_ENV=production
ENV PORT=5801
ENV HOSTNAME="0.0.0.0"

# Expose port
EXPOSE 5801

# Switch to non-root user
USER nextjs

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD wget -q --spider http://localhost:5801/ || exit 1

# Run standalone server
CMD ["node", "server.js"]
