ARG NODE_VERSION=24.15.0
ARG N8N_VERSION=snapshot
ARG IMAGE_TITLE="n8n"
ARG IMAGE_SOURCE="https://github.com/n8n-io/n8n"
ARG IMAGE_URL="https://n8n.io"
ARG IMAGE_REVISION=""
ARG MAIN_GITHUB_REPO_URL

# Builder stage exists because the runtime base image has no toolchain.
FROM node:${NODE_VERSION}-alpine3.22 AS builder
COPY ./compiled /usr/local/lib/node_modules/n8n
RUN apk add --no-cache python3 make g++ && \
    cd /usr/local/lib/node_modules/n8n && \
    npm rebuild sqlite3

FROM n8nio/base:${NODE_VERSION}

ARG N8N_VERSION
ARG N8N_RELEASE_TYPE=dev
ARG IMAGE_TITLE
ARG IMAGE_SOURCE
ARG IMAGE_URL
ARG IMAGE_REVISION
ARG MAIN_GITHUB_REPO_URL
ENV NODE_ENV=production
ENV N8N_RELEASE_TYPE=${N8N_RELEASE_TYPE}
ENV N8N_VERSION=${N8N_VERSION}
ENV N8N_MAIN_GITHUB_REPO_URL=${MAIN_GITHUB_REPO_URL}
ENV SHELL=/bin/sh

WORKDIR /home/node

COPY --from=builder /usr/local/lib/node_modules/n8n /usr/local/lib/node_modules/n8n
COPY docker/images/n8n/docker-entrypoint.sh /

RUN ln -s /usr/local/lib/node_modules/n8n/bin/n8n /usr/local/bin/n8n && \
    mkdir -p /home/node/.n8n && \
    chown -R node:node /home/node && \
    rm -rf /root/.npm /tmp/*

EXPOSE 5678/tcp
USER node
ENTRYPOINT ["tini", "--", "/docker-entrypoint.sh"]

LABEL org.opencontainers.image.title="${IMAGE_TITLE}" \
      org.opencontainers.image.description="Workflow Automation Tool" \
      org.opencontainers.image.source="${IMAGE_SOURCE}" \
      org.opencontainers.image.url="${IMAGE_URL}" \
      org.opencontainers.image.version=${N8N_VERSION} \
      org.opencontainers.image.revision="${IMAGE_REVISION}"
