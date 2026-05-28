ARG NODE_VERSION=24.15.0
ARG N8N_VERSION=snapshot
ARG IMAGE_TITLE="n8n"
ARG IMAGE_SOURCE="https://github.com/n8n-io/n8n"
ARG IMAGE_URL="https://n8n.io"
ARG IMAGE_REVISION=""
ARG MAIN_GITHUB_REPO_URL

# Builder stage exists because the runtime base image has no toolchain.
# Pinned to multi-arch index digest (linux/amd64 + linux/arm64) for reproducible builds.
# Bump the digest together with the tag when updating the base image.
FROM node:24.15.0-alpine3.22@sha256:b689d4005875ae167178471a7a622ec2909459a3bbb32277260be1971af7a99f AS builder
COPY ./compiled /usr/local/lib/node_modules/n8n
RUN apk add --no-cache python3 make g++ && \
    cd /usr/local/lib/node_modules/n8n && \
    npm rebuild sqlite3 && \
    # Rebuild isolated-vm from source. node-gyp-build's musl detection relies
    # on /etc/alpine-release which DHI Alpine omits, so the bundled prebuilt
    # loader picks the glibc binary and segfaults in musl pthread paths.
    # Removing prebuilds and invoking node-gyp directly avoids npm rebuild's
    # double-build behavior (built-in node-gyp + install-script node-gyp)
    # which races on dep-file state.
    rm -rf node_modules/isolated-vm/prebuilds && \
    cd node_modules/isolated-vm && \
    npx --yes node-gyp rebuild --release -j max

# Pinned to multi-arch index digest (linux/amd64 + linux/arm64) for reproducible builds.
# n8nio/base is republished by a separate workflow (docker/images/n8n-base) on every
# base change, so a base rebuild does not reach this image until the digest is
# manually re-pinned here. Bump the digest together with the tag whenever the base
# image is intentionally updated.
FROM n8nio/base:24.15.0@sha256:dade45d8a974e72bccbf57c13bc684b5dbb2f73e0ca7c837739e439de7b91aa9

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
