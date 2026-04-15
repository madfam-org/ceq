# CEQ Studio - Next.js Frontend
#
# Multi-stage build for production deployment with standalone output.

# =============================================================================
# Stage 1: Build the application
# =============================================================================
FROM node:20-alpine AS builder

WORKDIR /app

# Copy workspace root config + lockfile + all package.json files
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/studio/package.json ./apps/studio/
COPY packages/ui/package.json ./packages/ui/

# Full install — standalone tracer needs the complete .pnpm store
RUN corepack enable && corepack prepare pnpm@9.14.4 --activate && \
    pnpm install --frozen-lockfile || pnpm install

# Copy source code
COPY apps/studio/ ./apps/studio/
COPY packages/ ./packages/

# Build arguments for environment variables
ARG NEXT_PUBLIC_API_URL=https://api.ceq.lol
ARG NEXT_PUBLIC_WS_URL=wss://ws.ceq.lol
ARG NEXT_PUBLIC_JANUA_DOMAIN=auth.madfam.io
ARG NEXT_PUBLIC_JANUA_CLIENT_ID=jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk

ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL
ENV NEXT_PUBLIC_JANUA_DOMAIN=$NEXT_PUBLIC_JANUA_DOMAIN
ENV NEXT_PUBLIC_JANUA_CLIENT_ID=$NEXT_PUBLIC_JANUA_CLIENT_ID
ENV NEXT_TELEMETRY_DISABLED=1

# Build Next.js with standalone output
RUN pnpm --filter @ceq/studio build

# =============================================================================
# Stage 2: Production image
# =============================================================================
FROM node:20-alpine AS production

WORKDIR /app

# Create non-root user
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy standalone output
# Note: Next.js 14 with outputFileTracingRoot produces flat structure
# (server.js at root, node_modules/ with symlinks)
COPY --from=builder --chown=nextjs:nodejs /app/apps/studio/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/apps/studio/.next/static ./.next/static
COPY --from=builder /app/apps/studio/public ./public

# Fix broken pnpm symlinks: copy .pnpm store and recreate links
# Next.js 14 standalone doesn't trace .pnpm/ into output
RUN rm -rf node_modules
COPY --from=builder /app/node_modules/.pnpm ./node_modules/.pnpm
RUN ln -s .pnpm/next@14.2.35_@babel+core@7.29.0_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next ./node_modules/next && \
    ln -s .pnpm/react@18.3.1/node_modules/react ./node_modules/react && \
    ln -s .pnpm/react-dom@18.3.1_react@18.3.1/node_modules/react-dom ./node_modules/react-dom

# Environment
ENV NODE_ENV=production
ENV PORT=5801
ENV HOSTNAME="0.0.0.0"

EXPOSE 5801

USER nextjs

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD wget -q --spider http://localhost:5801/ || exit 1

CMD ["node", "server.js"]
