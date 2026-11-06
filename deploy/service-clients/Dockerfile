FROM louislam/uptime-kuma:2.5.9@sha256:e88415a90dd2f7efecdbc18de0490aff292764a3ac471531bf1d0481725591bd AS kuma-base
FROM vaultwarden/server:1.37.5@sha256:4fe17f415f90087377d37c755e0ea3cf189dcc6794e49cdd2a9adbb4937d9e1f AS vault-base

FROM --platform=$BUILDPLATFORM node:22-alpine AS patch
WORKDIR /patch
COPY logout.mjs .

FROM patch AS kuma-assets
COPY --from=kuma-base /app/dist/assets/index-KKUg83qb.js .
RUN node logout.mjs kuma

FROM patch AS vault-assets
COPY --from=vault-base /web-vault/app/main.1176a28a68b7b4809391.js .
COPY --from=vault-base /web-vault/index.html .
RUN node logout.mjs vault

FROM kuma-base AS kuma
COPY --from=kuma-assets /patch/out/ /app/dist/assets/

FROM vault-base AS vault
COPY --from=vault-assets /patch/out/ /web-vault/
