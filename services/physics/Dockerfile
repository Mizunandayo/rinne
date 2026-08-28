# syntax=docker/dockerfile:1.7
# docker build -f services/physics/Dockerfile -t rinne-physics:local .

FROM node:22.23.2-alpine3.23 AS base
ENV PNPM_HOME=/pnpm PATH=/pnpm:$PATH CI=true
# pnpm comes from npm, not corepack. The corepack bundled with node:22.11.0
# carries a stale set of npm registry signing keys and dies with
# "Cannot find matching keyid" verifying the pnpm tarball - npm rotated those
# keys after this base image was cut. Installing an exact version through npm
# keeps the version pinned AND keeps registry integrity verification on, without
# coupling the build to corepack's bundled key set. Disabling verification with
# COREPACK_INTEGRITY_KEYS=0 would "work" and is exactly the wrong trade here.
RUN npm install -g pnpm@10.11.0
WORKDIR /repo

FROM base AS deps
COPY pnpm-lock.yaml pnpm-workspace.yaml package.json .npmrc ./
COPY packages/contracts/package.json  packages/contracts/
COPY packages/scene/package.json      packages/scene/
COPY services/web/package.json        services/web/
COPY services/physics/package.json    services/physics/
RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store \
    pnpm install --frozen-lockfile

FROM deps AS build
COPY tsconfig.base.json ./
COPY packages/contracts packages/contracts
COPY packages/scene     packages/scene
COPY services/physics   services/physics
RUN pnpm --filter @rinne/contracts run build \
 && pnpm --filter @rinne/scene     run build \
 && pnpm --filter @rinne/physics   run build

# Production dependency tree only, resolved from the same lockfile.
FROM base AS prod-deps
COPY pnpm-lock.yaml pnpm-workspace.yaml package.json .npmrc ./
COPY packages/contracts/package.json  packages/contracts/
COPY packages/scene/package.json      packages/scene/
COPY services/web/package.json        services/web/
COPY services/physics/package.json    services/physics/
RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store \
    pnpm install --frozen-lockfile --prod \
      --filter @rinne/physics --filter @rinne/contracts --filter @rinne/scene

FROM node:22.23.2-alpine3.23 AS runtime
ENV NODE_ENV=production PORT=8080
RUN addgroup -g 10001 -S rinne && adduser -u 10001 -S rinne -G rinne
WORKDIR /repo

# pnpm links workspace packages with RELATIVE symlinks into node_modules/.pnpm.
COPY --from=prod-deps --chown=10001:10001 /repo/node_modules                   ./node_modules
COPY --from=prod-deps --chown=10001:10001 /repo/services/physics/node_modules  ./services/physics/node_modules
COPY --from=prod-deps --chown=10001:10001 /repo/packages/contracts/node_modules ./packages/contracts/node_modules
COPY --from=build     --chown=10001:10001 /repo/packages/contracts/dist        ./packages/contracts/dist
COPY --from=build     --chown=10001:10001 /repo/packages/contracts/package.json ./packages/contracts/package.json
COPY --from=prod-deps --chown=10001:10001 /repo/packages/scene/node_modules    ./packages/scene/node_modules
COPY --from=build     --chown=10001:10001 /repo/packages/scene/dist            ./packages/scene/dist
COPY --from=build     --chown=10001:10001 /repo/packages/scene/package.json    ./packages/scene/package.json
COPY --from=build     --chown=10001:10001 /repo/services/physics/dist          ./services/physics/dist
COPY --from=build     --chown=10001:10001 /repo/services/physics/package.json  ./services/physics/package.json

WORKDIR /repo/services/physics
USER 10001:10001
EXPOSE 8080
CMD ["node", "dist/server.js"]
