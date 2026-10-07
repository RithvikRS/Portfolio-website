# syntax=docker/dockerfile:1
FROM node:24-bookworm-slim AS build

ARG PNPM_VERSION=11.19.0
RUN npm install --global --ignore-scripts pnpm@${PNPM_VERSION}
WORKDIR /app

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile --prod --ignore-scripts

COPY scripts/ ./scripts/
COPY server/ ./server/
COPY tests/ ./tests/
COPY data/ ./data/
COPY css/ ./css/
COPY js/ ./js/
COPY images/ ./images/
COPY documents/ ./documents/
ARG SITE_URL
RUN node scripts/build.mjs && node scripts/check.mjs && node --test tests/*.test.mjs

FROM node:24-bookworm-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production HOST=0.0.0.0 PORT=4173

COPY --from=build /app/package.json ./
COPY --from=build /app/node_modules ./node_modules/
COPY --from=build /app/server ./server/
COPY --from=build /app/data ./data/
COPY --from=build /app/css ./css/
COPY --from=build /app/js ./js/
COPY --from=build /app/images ./images/
COPY --from=build /app/documents ./documents/
COPY --from=build /app/*.html /app/sitemap.xml ./

USER node
EXPOSE 4173
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["node", "--input-type=module", "-e", "const response = await fetch('http://127.0.0.1:4173/api/contact', { signal: AbortSignal.timeout(3000) }); if (!response.ok) process.exit(1);"]
CMD ["node", "server/index.mjs"]
