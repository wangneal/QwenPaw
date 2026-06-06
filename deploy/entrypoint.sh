#!/bin/sh
# Substitute QWENPAW_PORT in supervisord template and start supervisord.
# Default port 8088; override at runtime with -e QWENPAW_PORT=3000.
set -e

is_auth_enabled() {
  if [ "${QWENPAW_AUTH_ENABLED+x}" ]; then
    flag="${QWENPAW_AUTH_ENABLED}"
  else
    flag="${COPAW_AUTH_ENABLED:-}"
  fi
  flag="$(printf '%s' "$flag" | tr '[:upper:]' '[:lower:]')"
  [ "$flag" = "true" ] || [ "$flag" = "1" ] || [ "$flag" = "yes" ]
}

warn_if_auth_off_container_bind() {
  if is_auth_enabled; then
    return
  fi

  cat >&2 <<EOF
============================================================
SECURITY NOTICE: QwenPaw is running in Docker without authentication.

QwenPaw cannot verify whether access to the service is limited to a trusted
network. Anyone who can reach the service may access QwenPaw APIs without login.

Recommended:
  - Restrict access to a trusted network or protected environment.
  - Enable authentication with QWENPAW_AUTH_ENABLED=true if untrusted users or
    processes may reach the service.
============================================================
EOF
}

export starmind_WORKING_DIR="${starmind_WORKING_DIR:-${QWENPAW_WORKING_DIR:-/app/working}}"
export starmind_SECRET_DIR="${starmind_SECRET_DIR:-${QWENPAW_SECRET_DIR:-/app/working.secret}}"
export starmind_BACKUP_DIR="${starmind_BACKUP_DIR:-${QWENPAW_BACKUP_DIR:-/app/working.backups}}"
export QWENPAW_WORKING_DIR="${QWENPAW_WORKING_DIR:-${starmind_WORKING_DIR}}"
export QWENPAW_SECRET_DIR="${QWENPAW_SECRET_DIR:-${starmind_SECRET_DIR}}"
export QWENPAW_BACKUP_DIR="${QWENPAW_BACKUP_DIR:-${starmind_BACKUP_DIR}}"

# Auto-initialize if config.json is missing (bind mount with empty directory).
if [ ! -f "${starmind_WORKING_DIR}/config.json" ]; then
  echo "No config.json found in ${starmind_WORKING_DIR}"
  echo "Running initialization..."
  qwenpaw init --defaults --accept-security
  echo "Initialization complete!"
else
  echo "Config found in ${starmind_WORKING_DIR}, skipping initialization."
fi

# ── Sync built-in plugins to StarMind working directory ─────────────
# StarMind uses starmind_WORKING_DIR/plugins/.
# Always overwrite from /app/builtin-plugins/ so image updates take effect.
#
# IMPORTANT: Plugins must be placed FLAT (one level deep) under
#   ${starmind_WORKING_DIR}/plugins/<plugin-name>/plugin.json
# because PluginLoader.discover_plugins() only scans direct children of
# the plugins directory for plugin.json.  The /app/builtin-plugins/ image
# layout uses tool/ and frontend/ sub-directories for organisation, but
# we flatten them on sync so the loader can find every plugin.
_STARMIND_PLUGINS_DIR="${starmind_WORKING_DIR}/plugins"
if [ -d "/app/builtin-plugins" ]; then
  echo "Syncing built-in plugins to ${_STARMIND_PLUGINS_DIR}..."
  # Tool plugins — flatten into plugins/<name>/
  for plugin_dir in /app/builtin-plugins/tool/*/; do
    [ -d "$plugin_dir" ] || continue
    plugin_name=$(basename "$plugin_dir")
    target="${_STARMIND_PLUGINS_DIR}/${plugin_name}"
    # Remove old __pycache__ to avoid stale bytecode
    if [ -d "$target" ]; then
      find "$target" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
      rm -rf "$target"
    fi
    mkdir -p "${_STARMIND_PLUGINS_DIR}"
    cp -rf "$plugin_dir" "$target"
    echo "  ✓ Synced tool plugin: $plugin_name"
  done
  # Frontend plugins — flatten into plugins/<name>/
  for plugin_dir in /app/builtin-plugins/frontend/*/; do
    [ -d "$plugin_dir" ] || continue
    plugin_name=$(basename "$plugin_dir")
    target="${_STARMIND_PLUGINS_DIR}/${plugin_name}"
    if [ -d "$target" ]; then
      rm -rf "$target"
    fi
    mkdir -p "${_STARMIND_PLUGINS_DIR}"
    cp -rf "$plugin_dir" "$target"
    echo "  ✓ Synced frontend plugin: $plugin_name"
  done
fi

/app/venv/bin/python /app/scripts/sync_starmind_extensions.py

export QWENPAW_PORT="${QWENPAW_PORT:-8088}"
warn_if_auth_off_container_bind
envsubst '${QWENPAW_PORT}' \
  < /etc/supervisor/conf.d/supervisord.conf.template \
  > /etc/supervisor/conf.d/supervisord.conf
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
