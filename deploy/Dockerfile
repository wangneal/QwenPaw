# -----------------------------------------------------------------------------
# Stage 1: build console frontend (dist not committed in repo).
# -----------------------------------------------------------------------------
FROM docker.1ms.run/node:20-slim AS console-builder
WORKDIR /app
COPY console /app/console
RUN cd /app/console && npm ci --include=dev --registry=https://registry.npmmirror.com && npm run build

# -----------------------------------------------------------------------------
# Stage 1b: build bundled Kingdee admin frontend plugin (dist is dockerignored).
# -----------------------------------------------------------------------------
FROM docker.1ms.run/node:20-slim AS kingdee-admin-builder
WORKDIR /app
COPY plugins/frontend/kingdee-erp-admin/ui /app/ui
RUN cd /app/ui && npm ci --include=dev --registry=https://registry.npmmirror.com && npm run build

# -----------------------------------------------------------------------------
# Stage 2: runtime image with Python, Chromium, and app.
# -----------------------------------------------------------------------------
FROM docker.1ms.run/node:20-slim

# ENV variables
ENV NODE_ENV=production
ENV WORKSPACE_DIR=/app
ENV starmind_WORKING_DIR=/app/working
ENV starmind_SECRET_DIR=/app/working.secret
ENV starmind_BACKUP_DIR=/app/working.backups
ENV starmind_RUNNING_IN_CONTAINER=1
ENV QWENPAW_WORKING_DIR=/app/working
ENV QWENPAW_SECRET_DIR=/app/working.secret
ENV QWENPAW_BACKUP_DIR=/app/working.backups
ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

# Channel filtering: use QWENPAW_DISABLED_CHANNELS (exclusion, recommended)
# or QWENPAW_ENABLED_CHANNELS (whitelist). Override at runtime with -e.
ARG QWENPAW_DISABLED_CHANNELS="imessage"
ENV QWENPAW_DISABLED_CHANNELS=${QWENPAW_DISABLED_CHANNELS}
ARG QWENPAW_ENABLED_CHANNELS=""
ENV QWENPAW_ENABLED_CHANNELS=${QWENPAW_ENABLED_CHANNELS}

ARG DEBIAN_FRONTEND=noninteractive

# ── apt: keep default deb.debian.org (accessible from Docker build) ─────

RUN apt-get update && apt-get install -y --fix-missing \
    curl  \
    python3  \
    python3-pip  \
    python3-venv \
    build-essential  \
    libssl-dev  \
    git  \
    supervisor  \
    vim  \
    gettext-base \
    xfce4 \
    xfce4-terminal \
    xvfb \
    dbus-x11 \
    fonts-wqy-zenhei \
    fonts-wqy-microhei \
  && rm -rf /var/lib/apt/lists/* \
  && apt-get clean


RUN apt-get update && apt-get install -y --fix-missing \
    chromium \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxtst6 \
    libnss3 \
    libglib2.0-0 \
    libdrm2 \
    libgbm1 \
    libasound2 \
    fonts-liberation \
    libu2f-udev \
  && rm -rf /var/lib/apt/lists/* \
  && apt-get clean


RUN sed -i 's/^CHROMIUM_FLAGS=""/CHROMIUM_FLAGS="--no-sandbox"/' /usr/bin/chromium

# Playwright: use system Chromium (already installed above).
ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium
# Avoid Playwright downloading its own browser when executable_path is used.
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
# Indicate running in container (used e.g. for Chromium --no-sandbox).
ENV QWENPAW_RUNNING_IN_CONTAINER=1

WORKDIR ${WORKSPACE_DIR}

RUN python3 -m venv venv
ENV PATH="/app/venv/bin:$PATH"

COPY pyproject.toml setup.py ./

# ── Install uv via pip (avoids ghcr.io which is blocked in China) ────────
RUN pip install uv && rm -rf /root/.cache/pip
# Install third-party dependencies before copying src so normal code changes
# do not invalidate the expensive dependency layer.
RUN python3 -c "import subprocess, tomllib; deps = tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']; subprocess.check_call(['uv', 'pip', 'install', '--no-cache-dir', *deps])"

COPY src ./src
# Inject console dist from build stage (repo does not commit dist).
COPY --from=console-builder /app/console/dist/ ./src/qwenpaw/console/
RUN uv pip install --no-cache-dir --no-deps . && rm -rf ./build

# ── Install Kingdee SDK ──────────────────────────────────────────────────
COPY plugins/tool/kingdee-erp/backends/kingdee/*.whl /tmp/kd-sdk/
RUN pip install /tmp/kd-sdk/*.whl && rm -rf /tmp/kd-sdk
COPY plugins/tool/kingdee-erp/requirements.txt /tmp/kingdee-erp-requirements.txt
RUN pip install --disable-pip-version-check --no-cache-dir -r /tmp/kingdee-erp-requirements.txt \
  && rm -f /tmp/kingdee-erp-requirements.txt

# ── Copy ERP plugins to built-in plugin directory ────────────────────
# These will be loaded on first startup by entrypoint.sh.
COPY plugins/tool/kingdee-erp/ /app/builtin-plugins/tool/kingdee-erp/
COPY plugins/frontend/kingdee-erp-admin/ /app/builtin-plugins/frontend/kingdee-erp-admin/
COPY --from=kingdee-admin-builder /app/ui/dist/ /app/builtin-plugins/frontend/kingdee-erp-admin/ui/dist/


# QwenPaw app port (default 8088). Override at runtime with -e QWENPAW_PORT=3000.
ENV QWENPAW_PORT=8088

RUN mkdir -p /app/scripts
COPY deploy/sync_starmind_extensions.py /app/scripts/sync_starmind_extensions.py
COPY deploy/config/supervisord.conf.template /etc/supervisor/conf.d/supervisord.conf.template
COPY --chmod=755 deploy/entrypoint.sh /entrypoint.sh

EXPOSE 8088

CMD ["/entrypoint.sh"]
