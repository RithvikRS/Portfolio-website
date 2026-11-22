# Keep the published runtime and inference code byte-for-byte unchanged.
FROM ghcr.io/cheaper-inference/omniroute:3.8.53@sha256:b52a17661a1aff42ffb78f349f423e986dfc55b57274f28559f8387622ef8ee4 AS upstream
FROM upstream AS labels
USER root
COPY cost-labels.mjs cost-labels.json /tmp/cost-labels/
RUN node /tmp/cost-labels/cost-labels.mjs /app/.build/next/server/chunks/22453.js /tmp/22453.js \
    && node --check /tmp/22453.js
FROM upstream
COPY --from=labels --chown=1000:1000 /tmp/22453.js /app/.build/next/server/chunks/22453.js
