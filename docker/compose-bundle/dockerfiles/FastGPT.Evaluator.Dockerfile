ARG NODE_IMAGE=node:20.19.5-bookworm
FROM ${NODE_IMAGE}

USER root
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG PR_ID
ARG BASE_COMMIT
ARG FASTGPT_REPO=https://github.com/labring/FastGPT.git
ARG PNPM_VERSION=10.33.4
ARG BUN_VERSION=1.1.45
ARG INSTALL_BUN=false
ARG NPM_REGISTRY=

ENV DEBIAN_FRONTEND=noninteractive
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
ENV PNPM_HOME=/opt/pnpm
ENV BUN_INSTALL=/opt/bun
ENV PATH=/opt/pnpm:/opt/bun/bin:${PATH}
ENV CI=true
ENV NODE_OPTIONS=--max-old-space-size=8192

LABEL org.opencontainers.image.title="RepoACES FastGPT PR evaluator"
LABEL org.opencontainers.image.description="Per-PR deterministic FastGPT evaluator image for RepoACES."
LABEL repoaces.pr_id="${PR_ID}"
LABEL repoaces.base_commit="${BASE_COMMIT}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      bash \
      build-essential \
      ca-certificates \
      curl \
      git \
      jq \
      pkg-config \
      python3 \
      ripgrep \
      unzip \
      xz-utils \
    && rm -rf /var/lib/apt/lists/*

RUN if ! command -v docker >/dev/null 2>&1; then \
      apt-get update \
      && apt-get install -y --no-install-recommends docker.io \
      && rm -rf /var/lib/apt/lists/*; \
    fi \
    && if ! docker compose version >/dev/null 2>&1 && ! command -v docker-compose >/dev/null 2>&1; then \
      apt-get update \
      && apt-get install -y --no-install-recommends docker-compose \
      && rm -rf /var/lib/apt/lists/*; \
    fi

RUN if [[ -n "${NPM_REGISTRY}" ]]; then npm config set registry "${NPM_REGISTRY}"; fi \
    && mkdir -p "${PNPM_HOME}" \
    && corepack enable \
    && corepack prepare "pnpm@${PNPM_VERSION}" --activate \
    && npm install -g --force "pnpm@${PNPM_VERSION}" \
    && if [[ "${INSTALL_BUN}" == "true" ]]; then \
      curl -fsSL https://bun.sh/install | bash -s -- "bun-v${BUN_VERSION}" \
      && ln -sf /opt/bun/bin/bun /usr/local/bin/bun; \
    fi \
    && node --version \
    && npm --version \
    && pnpm --version \
    && if [[ "${INSTALL_BUN}" == "true" ]]; then bun --version; else echo "bun install skipped"; fi \
    && git --version \
    && docker --version

RUN test -n "${PR_ID}" \
    && test -n "${BASE_COMMIT}" \
    && cd / \
    && rm -rf /workspace \
    && mkdir -p /workspace \
    && git clone --no-checkout "${FASTGPT_REPO}" /workspace \
    && pr_number="${PR_ID##*-}" \
    && git -C /workspace fetch origin "pull/${pr_number}/head:refs/remotes/origin/pr-${pr_number}-head" --no-tags || true \
    && git -C /workspace checkout --force "${BASE_COMMIT}" \
    && git -C /workspace reset --hard "${BASE_COMMIT}" \
    && git -C /workspace clean -fdx

WORKDIR /workspace

RUN pnpm install --frozen-lockfile

COPY runtime/ /opt/repoaces-pr/
COPY configs/${PR_ID}.eval.json /opt/repoaces-pr/eval.json
RUN chmod +x /opt/repoaces-pr/*.sh

ENTRYPOINT ["/opt/repoaces-pr/run-eval.sh"]
CMD ["all"]
