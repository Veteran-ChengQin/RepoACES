ARG OH_BASE_IMAGE=ghcr.io/openhands/agent-server:1.26.0-python
FROM ${OH_BASE_IMAGE}

USER root
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG PR_ID
ARG BASE_COMMIT
ARG FASTGPT_REPO=https://github.com/labring/FastGPT.git
ARG PNPM_VERSION=10.33.4
ARG NODE_VERSION=20.19.5
ARG BUN_VERSION=1.1.45
ARG INSTALL_BUN=false
ARG NPM_REGISTRY=
ARG RUN_COMMON_CHECKS=false

ENV DEBIAN_FRONTEND=noninteractive
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
ENV PNPM_HOME=/opt/pnpm
ENV BUN_INSTALL=/opt/bun
ENV PATH=/opt/node/bin:/opt/pnpm:/opt/bun/bin:${PATH}
ENV CI=true
ENV NODE_OPTIONS=--max-old-space-size=8192
ENV GIT_TERMINAL_PROMPT=0
ENV REPOACES_WORKSPACE=/workspace
ENV REPOACES_OH_ASSETS=/opt/repoaces-oh

LABEL org.opencontainers.image.title="RepoACES FastGPT OpenHands workspace"
LABEL org.opencontainers.image.description="Per-PR FastGPT workspace image for OpenHands repository-wide build and test feedback."
LABEL repoaces.kind="openhands-workspace"
LABEL repoaces.pr_id="${PR_ID}"
LABEL repoaces.base_commit="${BASE_COMMIT}"

RUN for attempt in 1 2 3; do \
      apt-get update \
      && apt-get install -y --no-install-recommends -o Acquire::Retries=3 \
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
      && rm -rf /var/lib/apt/lists/* \
      && break; \
      if [[ "${attempt}" == "3" ]]; then exit 1; fi; \
      echo "apt install failed, retrying in $((attempt * 5)) seconds..." >&2; \
      rm -rf /var/lib/apt/lists/*; \
      sleep $((attempt * 5)); \
    done

RUN if ! command -v docker >/dev/null 2>&1; then \
      for attempt in 1 2 3; do \
        apt-get update \
        && apt-get install -y --no-install-recommends -o Acquire::Retries=3 docker.io \
        && rm -rf /var/lib/apt/lists/* \
        && break; \
        if [[ "${attempt}" == "3" ]]; then exit 1; fi; \
        echo "docker apt install failed, retrying in $((attempt * 5)) seconds..." >&2; \
        rm -rf /var/lib/apt/lists/*; \
        sleep $((attempt * 5)); \
      done; \
    fi \
    && if ! docker compose version >/dev/null 2>&1 && ! command -v docker-compose >/dev/null 2>&1; then \
      for attempt in 1 2 3; do \
        apt-get update \
        && apt-get install -y --no-install-recommends -o Acquire::Retries=3 docker-compose \
        && rm -rf /var/lib/apt/lists/* \
        && break; \
        if [[ "${attempt}" == "3" ]]; then exit 1; fi; \
        echo "docker-compose apt install failed, retrying in $((attempt * 5)) seconds..." >&2; \
        rm -rf /var/lib/apt/lists/*; \
        sleep $((attempt * 5)); \
      done; \
    fi

RUN curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" -o /tmp/node.tar.xz \
    && rm -rf /opt/node \
    && mkdir -p /opt/node \
    && tar -xJf /tmp/node.tar.xz -C /opt/node --strip-components=1 \
    && rm -f /tmp/node.tar.xz \
    && if [[ -n "${NPM_REGISTRY}" ]]; then npm config set registry "${NPM_REGISTRY}"; fi \
    && npm install -g --force "pnpm@${PNPM_VERSION}" \
    && ln -sf /opt/node/bin/node /usr/local/bin/node \
    && ln -sf /opt/node/bin/npm /usr/local/bin/npm \
    && ln -sf /opt/node/bin/npx /usr/local/bin/npx \
    && ln -sf /opt/node/bin/pnpm /usr/local/bin/pnpm \
    && if [[ "${INSTALL_BUN}" == "true" ]]; then \
      curl -fsSL https://bun.sh/install | bash -s -- "bun-v${BUN_VERSION}" \
      && ln -sf /opt/bun/bin/bun /usr/local/bin/bun; \
    fi \
    && node --version \
    && npm --version \
    && pnpm --version \
    && git --version \
    && docker --version

RUN test -n "${PR_ID}" \
    && test -n "${BASE_COMMIT}" \
    && rm -rf "${REPOACES_WORKSPACE}" \
    && mkdir -p "${REPOACES_WORKSPACE}" \
    && for attempt in 1 2 3; do \
      rm -rf "${REPOACES_WORKSPACE}" \
      && git clone --no-checkout "${FASTGPT_REPO}" "${REPOACES_WORKSPACE}" \
      && break; \
      if [[ "${attempt}" == "3" ]]; then exit 1; fi; \
      echo "git clone failed, retrying in $((attempt * 5)) seconds..." >&2; \
      sleep $((attempt * 5)); \
    done \
    && if ! git -C "${REPOACES_WORKSPACE}" checkout --force "${BASE_COMMIT}"; then \
      pr_number="${PR_ID##*-}" \
      && for attempt in 1 2 3; do \
        git -C "${REPOACES_WORKSPACE}" fetch origin "pull/${pr_number}/head:refs/remotes/origin/pr-${pr_number}" \
        && break; \
        if [[ "${attempt}" == "3" ]]; then exit 1; fi; \
        echo "git fetch PR ref failed, retrying in $((attempt * 5)) seconds..." >&2; \
        sleep $((attempt * 5)); \
      done \
      && git -C "${REPOACES_WORKSPACE}" checkout --force "${BASE_COMMIT}"; \
    fi \
    && git -C "${REPOACES_WORKSPACE}" reset --hard "${BASE_COMMIT}" \
    && git -C "${REPOACES_WORKSPACE}" clean -fdx

WORKDIR /workspace

RUN required_pnpm="$(node -e "const fs=require('fs'); const p=JSON.parse(fs.readFileSync('package.json','utf8')); const pm=(p.packageManager||'').match(/^pnpm@(.+)$/); process.stdout.write((pm&&pm[1]) || (p.engines&&p.engines.pnpm) || '');")" \
    && if [[ -n "${required_pnpm}" ]]; then \
      pnpm_target="${required_pnpm}"; \
      if [[ "${pnpm_target}" =~ ^([0-9]+)\.x$ ]]; then \
        required_major="${BASH_REMATCH[1]}"; \
        if [[ "${PNPM_VERSION}" == "${required_major}."* ]]; then \
          pnpm_target="${PNPM_VERSION}"; \
        else \
          pnpm_target="${required_major}"; \
        fi; \
      fi; \
      echo "FastGPT base commit requires pnpm ${required_pnpm}; installing pnpm@${pnpm_target}"; \
      npm install -g --force "pnpm@${pnpm_target}"; \
      ln -sf /opt/node/bin/pnpm /usr/local/bin/pnpm; \
    fi \
    && pnpm --version

COPY runtime/install-fastgpt-deps.sh /opt/repoaces-oh/install-fastgpt-deps.sh

RUN chmod +x /opt/repoaces-oh/install-fastgpt-deps.sh \
    && /opt/repoaces-oh/install-fastgpt-deps.sh \
    && if [[ "${RUN_COMMON_CHECKS}" == "true" ]]; then \
      node --version && pnpm --version && git diff --check; \
    fi

COPY runtime/docker-compose-config.sh /opt/repoaces-oh/docker-compose-config.sh
COPY runtime/openhands-common-commands.sh /opt/repoaces-oh/openhands-common-commands.sh
COPY runtime/compose.env /opt/repoaces-oh/compose.env

RUN chmod +x /opt/repoaces-oh/docker-compose-config.sh \
    && chmod +x /opt/repoaces-oh/openhands-common-commands.sh

WORKDIR /workspace
