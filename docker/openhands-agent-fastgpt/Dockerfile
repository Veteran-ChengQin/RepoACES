ARG BASE_IMAGE=ghcr.io/openhands/agent-server:1.26.0-python
FROM ${BASE_IMAGE}

USER root
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG TARGETARCH
ARG NODE_VERSION=20.19.5
ARG PNPM_VERSION=10.11.0
ARG NPM_REGISTRY=

ENV DEBIAN_FRONTEND=noninteractive
ENV NODE_HOME=/opt/node-v${NODE_VERSION}
ENV PNPM_HOME=/home/openhands/.local/share/pnpm
ENV PATH=${PNPM_HOME}:/home/openhands/.local/bin:${NODE_HOME}/bin:${PATH}
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
ENV COREPACK_HOME=/home/openhands/.cache/node/corepack
ENV OPENHANDS_SUPPRESS_BANNER=1

LABEL org.opencontainers.image.title="RepoACES OpenHands FastGPT Agent Server"
LABEL org.opencontainers.image.description="OpenHands agent-server image with Node 20 and pnpm 10 for FastGPT/Dify coding tasks."

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      build-essential \
      ca-certificates \
      curl \
      git \
      jq \
      pkg-config \
      ripgrep \
      unzip \
      xz-utils \
    && rm -rf /var/lib/apt/lists/*

RUN case "${TARGETARCH:-amd64}" in \
      amd64) node_arch="x64" ;; \
      arm64) node_arch="arm64" ;; \
      *) echo "Unsupported Docker TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
    && mkdir -p /opt \
    && curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-${node_arch}.tar.xz" -o /tmp/node.tar.xz \
    && tar -xJf /tmp/node.tar.xz -C /opt \
    && mv "/opt/node-v${NODE_VERSION}-linux-${node_arch}" "${NODE_HOME}" \
    && rm -f /tmp/node.tar.xz \
    && ln -sf "${NODE_HOME}/bin/node" /usr/local/bin/node \
    && ln -sf "${NODE_HOME}/bin/npm" /usr/local/bin/npm \
    && ln -sf "${NODE_HOME}/bin/npx" /usr/local/bin/npx \
    && ln -sf "${NODE_HOME}/bin/corepack" /usr/local/bin/corepack

RUN if [[ -n "${NPM_REGISTRY}" ]]; then \
      npm config set registry "${NPM_REGISTRY}"; \
    fi \
    && mkdir -p "${PNPM_HOME}" \
    && npm install -g "pnpm@${PNPM_VERSION}" \
    && ln -sf "${NODE_HOME}/bin/pnpm" /usr/local/bin/pnpm \
    && node --version \
    && npm --version \
    && pnpm --version \
    && git --version \
    && rg --version | head -1

RUN mkdir -p "${PNPM_HOME}" "${COREPACK_HOME}" /home/openhands/.local/bin \
    && chown -R openhands:openhands /home/openhands/.local /home/openhands/.cache

WORKDIR /workspace
USER openhands
