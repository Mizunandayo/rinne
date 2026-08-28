# syntax=docker/dockerfile:1.7
FROM node:22.23.2-alpine3.23 AS base
ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH \
    CI=true \
    NEXT_TELEMETRY_DISABLED=1
# pnpm comes from npm, not corepack. The corepack bundled with node:22.11.0
# carries a stale set of npm registry signing keys and dies with
# "Cannot find matching keyid" verifying the pnpm tarball - npm rotated those
# keys after this base image was cut. Installing an exact version through npm
# keeps the version pinned AND keeps registry integrity verification on, without
# coupling the build to corepack's bundled key set. Disabling verification with
# COREPACK_INTEGRITY_KEYS=0 would "work" and is exactly the wrong trade here.
RUN npm install -g pnpm@10.11.0
WORKDIR /repo

# ── Dependencies ─────────────────────────────────────────────────────
FROM base AS deps
COPY pnpm-lock.yaml pnpm-workspace.yaml package.json .npmrc ./
COPY packages/contracts/package.json  packages/contracts/
COPY packages/scene/package.json      packages/scene/
COPY services/web/package.json        services/web/
COPY services/physics/package.json    services/physics/
RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store \
    pnpm install --frozen-lockfile

# ── Build ────────────────────────────────────────────────────────────
FROM deps AS build
COPY tsconfig.base.json ./
COPY packages/contracts packages/contracts
COPY packages/scene     packages/scene
COPY services/web       services/web
RUN pnpm --filter @rinne/contracts run build \
 && pnpm --filter @rinne/scene     run build \
 && pnpm --filter @rinne/web       run build

# ── Runtime ──────────────────────────────────────────────────────────
FROM node:22.23.2-alpine3.23 AS runtime
ENV NODE_ENV=production \
    PORT=8080 \
    HOSTNAME=0.0.0.0 \
    NEXT_TELEMETRY_DISABLED=1
WORKDIR /app

RUN addgroup -g 10001 -S rinne && adduser -u 10001 -S rinne -G rinne

COPY --from=build --chown=10001:10001 /repo/services/web/.next/standalone ./
COPY --from=build --chown=10001:10001 /repo/services/web/.next/static      ./services/web/.next/static
COPY --from=build --chown=10001:10001 /repo/services/web/public            ./services/web/public

USER 10001:10001
EXPOSE 8080
CMD ["node", "services/web/server.js"]
