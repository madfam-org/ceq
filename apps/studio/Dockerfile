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
    pnpm install --frozen-lockfile

# Copy source code
COPY apps/studio/ ./apps/studio/
COPY packages/ ./packages/

# Build arguments for environment variables
ARG NEXT_PUBLIC_API_URL=https://api.ceq.lol
ARG NEXT_PUBLIC_WS_URL=wss://ws.ceq.lol
ARG NEXT_PUBLIC_JANUA_URL=https://auth.madfam.io
ARG NEXT_PUBLIC_JANUA_CLIENT_ID=jnc_2EJwBz8xGVsGYOO2r3ck5CJH7YrQw4Yk
ARG NEXT_PUBLIC_DHANAM_BILLING_URL=https://api.dhan.am
ARG NEXT_PUBLIC_CEQ_CHECKOUT_ENABLED=false

ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL
ENV NEXT_PUBLIC_JANUA_URL=$NEXT_PUBLIC_JANUA_URL
ENV NEXT_PUBLIC_JANUA_CLIENT_ID=$NEXT_PUBLIC_JANUA_CLIENT_ID
ENV NEXT_PUBLIC_DHANAM_BILLING_URL=$NEXT_PUBLIC_DHANAM_BILLING_URL
ENV NEXT_PUBLIC_CEQ_CHECKOUT_ENABLED=$NEXT_PUBLIC_CEQ_CHECKOUT_ENABLED
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

# Copy standalone output.
# With outputFileTracingRoot at the monorepo root, Next.js emits the server
# entrypoint at apps/studio/server.js (not /app/server.js). The 2026-05-18
# production crash was caused by CMD ["node", "server.js"] against this layout.
COPY --from=builder --chown=nextjs:nodejs /app/apps/studio/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/apps/studio/.next/static ./apps/studio/.next/static
COPY --from=builder /app/apps/studio/public ./apps/studio/public

# The process entry, and why the CMD below names it rather than server.js.
#
# Next copies its internal router signal `x-middleware-rewrite` onto the
# CLIENT response for every rewrite, with no origin check — so `GET /` on
# ceq.lol answers every anonymous visitor with `x-middleware-rewrite: /landing`.
# Measured on this repo's own standalone output at 14.2.35 and again at 15.5.27. It cannot be removed inside
# src/middleware.ts (Next reads the rewrite out of that very response object, so
# deleting it there cancels the rewrite and serves a blank 200) and the
# next.config.mjs `headers()` entries are applied earlier in the route list than
# the branch that writes it. server-entry.mjs drops it on the Node response
# after routing is already decided. See that file's header for the two lines of
# Next this rests on.
COPY --from=builder --chown=nextjs:nodejs /app/apps/studio/server-entry.mjs ./apps/studio/server-entry.mjs

# Fix broken pnpm symlinks: copy .pnpm store and recreate links
# The standalone output doesn't trace the whole .pnpm/ store.
# The store directory names carry pnpm's peer suffix, so they must match
# pnpm-lock.yaml exactly; the `test -e` lines fail the build on a dangling link.
RUN rm -rf node_modules
COPY --from=builder /app/node_modules/.pnpm ./node_modules/.pnpm
RUN ln -s .pnpm/next@15.5.27_@babel+core@7.29.0_@playwright+test@1.60.0_@types+node@22.19.17_react-dom@19.3.0_react@19.3.0__react@19.3.0/node_modules/next ./node_modules/next && \
    ln -s .pnpm/react@19.3.0/node_modules/react ./node_modules/react && \
    ln -s .pnpm/react-dom@19.3.0_react@19.3.0/node_modules/react-dom ./node_modules/react-dom && \
    test -e node_modules/next/package.json && \
    test -e node_modules/react/package.json && \
    test -e node_modules/react-dom/package.json

# Environment
ENV NODE_ENV=production
ENV PORT=5801
ENV HOSTNAME="0.0.0.0"

EXPOSE 5801

USER nextjs

# Fail the image build if either entrypoint is missing or the filter has been
# gutted.
#
# The CMD names a file; nothing else checks that the file exists, still filters,
# or still hands over to the server it wraps — and all three failures look
# identical at runtime: a container that starts, passes its healthcheck, and
# publishes the internal route name of every rewrite. Do not weaken any of these
# to a warning, which is the same as deleting them but harder to notice.
RUN set -eu; \
    test -f apps/studio/server.js || { \
      echo "FATAL: apps/studio/server.js missing (outputFileTracingRoot layout)." >&2; \
      exit 1; \
    }; \
    entry="apps/studio/server-entry.mjs"; \
    if [ ! -f "$entry" ]; then \
      echo "FATAL: $entry is missing from the image." >&2; \
      echo "The CMD starts it, so the container cannot boot at all." >&2; \
      exit 1; \
    fi; \
    if ! grep -q 'x-middleware-rewrite' "$entry"; then \
      echo "FATAL: $entry no longer filters x-middleware-rewrite." >&2; \
      echo "The pod would start, pass its healthcheck, and answer every visitor" >&2; \
      echo "to ceq.lol with the internal route the middleware chose." >&2; \
      exit 1; \
    fi; \
    if ! grep -qE "await import\(['\"]\./server\.js['\"]\)" "$entry"; then \
      echo "FATAL: $entry does not hand over to ./server.js." >&2; \
      echo "The container would install a filter and then serve nothing." >&2; \
      exit 1; \
    fi; \
    echo "studio entrypoint and response-header filter present"

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD wget -q --spider http://localhost:5801/ || exit 1

CMD ["node", "apps/studio/server-entry.mjs"]
