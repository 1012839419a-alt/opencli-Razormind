#!/usr/bin/env sh

# Sourceable restart-recovery helpers shared by the Unix installer and its
# executable contract tests.  This file intentionally has no top-level side
# effects.

OPENCLI_RESTART_STATE_FILE_NAME=".opencli-restart-recovery-state"

opencli_is_wsl() {
  if [ -r /proc/sys/kernel/osrelease ] && grep -qi microsoft /proc/sys/kernel/osrelease; then
    return 0
  fi
  if [ -r /proc/version ] && grep -qi microsoft /proc/version; then
    return 0
  fi
  return 1
}

opencli_docker_boot_prerequisite_verified() {
  [ "$(uname -s 2>/dev/null || true)" = "Linux" ] || return 1
  opencli_is_wsl && return 1
  [ -z "${DOCKER_HOST:-}" ] || return 1
  [ "$(docker context show 2>/dev/null || true)" = "default" ] || return 1
  command -v systemctl >/dev/null 2>&1 || return 1
  systemctl is-enabled docker >/dev/null 2>&1
}

opencli_shell_quote() {
  # POSIX single-quote encoding.  The result is shell source, not display text.
  printf "'"
  printf '%s' "$1" | sed "s/'/'\"'\"'/g"
  printf "'"
}

opencli_state_value() {
  state_file="$1"
  state_key="$2"
  awk -v key="$state_key" 'index($0, key "=") == 1 { print substr($0, length(key) + 2); exit }' "$state_file"
}

opencli_assert_recovered_container() {
  service="$1"
  container_id="$(docker compose ps -q "$service")" || return 1
  [ -n "$container_id" ] || return 1
  state="$(docker inspect --format '{{.State.Status}}' "$container_id")" || return 1
  [ "$state" = "running" ] || return 1
  health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id")" || return 1
  [ "$health" = "healthy" ] || return 1
  printf '%s' "$container_id"
}

opencli_assert_valid_local_auth_state() {
  api_id="$1"
  docker exec "$api_id" python -c 'import base64, hashlib; from pathlib import Path; from backend.security.local_auth import load_password_hash; state=Path("/data/local-admin-password.hash"); marker=state.with_name(f"{state.name}.initialized"); assert marker.read_text(encoding="utf-8") in {"opencli-local-auth-state-v1:initial\n", "opencli-local-auth-state-v1:changed\n"}; encoded=load_password_hash("", str(state)); assert encoded; scheme,n_text,r_text,p_text,salt_text,expected_text=encoded.split("$", 5); n,r,p=map(int, (n_text,r_text,p_text)); assert scheme == "scrypt" and n >= 2 and n & (n - 1) == 0 and 0 < r <= 32 and 0 < p <= 16; decode=lambda value: base64.b64decode(value.encode("ascii"), altchars=b"-_", validate=True); salt=decode(salt_text); expected=decode(expected_text); assert len(salt) >= 16 and len(expected) >= 32; probe=hashlib.scrypt(b"opencli-restart-state-validation", salt=salt, n=n, r=r, p=p, maxmem=64 * 1024 * 1024); assert len(probe) == len(expected)' || return 1
}

opencli_prepare_restart_state() {
  install_dir="$1"
  compose_project_name="$2"
  sentinel="$3"
  state_file="$install_dir/$OPENCLI_RESTART_STATE_FILE_NAME"
  state_temp="$state_file.tmp"

  api_id="$(opencli_assert_recovered_container api)" || return 1
  agent_id="$(opencli_assert_recovered_container agent-1)" || return 1
  db_revision="$(docker exec "$api_id" python -c 'import sqlite3; db=sqlite3.connect("/data/opencli_admin.db"); print(db.execute("SELECT version_num FROM alembic_version").fetchone()[0])')" || return 1
  opencli_assert_valid_local_auth_state "$api_id" || return 1
  profile_volume="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/home/chrome/.config/chromium"}}{{.Name}}{{end}}{{end}}' "$agent_id")" || return 1
  [ -n "$profile_volume" ] || return 1

  docker exec "$api_id" python -c 'from pathlib import Path; import sys; Path("/data/.opencli-host-restart-sentinel").write_text(sys.argv[1], encoding="utf-8")' "$sentinel" || return 1
  docker exec "$agent_id" sh -c 'test -d /home/chrome/.config/chromium && test -r /home/chrome/.config/chromium && test -w /home/chrome/.config/chromium' || return 1
  docker exec "$agent_id" sh -c 'printf %s "$1" > /home/chrome/.config/chromium/.opencli-host-restart-sentinel' sh "$sentinel" || return 1

  umask 077
  {
    printf 'COMPOSE_PROJECT_NAME=%s\n' "$compose_project_name"
    printf 'DB_REVISION=%s\n' "$db_revision"
    printf 'AGENT_PROFILE_VOLUME=%s\n' "$profile_volume"
    printf 'SENTINEL=%s\n' "$sentinel"
  } > "$state_temp" || return 1
  chmod 600 "$state_temp" || return 1
  mv "$state_temp" "$state_file" || return 1
}

opencli_verify_restart_state() {
  install_dir="$1"
  state_file="$install_dir/$OPENCLI_RESTART_STATE_FILE_NAME"
  [ -r "$state_file" ] || {
    echo "Restart baseline is unavailable: $state_file" >&2
    return 1
  }

  expected_project="$(opencli_state_value "$state_file" COMPOSE_PROJECT_NAME)" || return 1
  expected_db_revision="$(opencli_state_value "$state_file" DB_REVISION)" || return 1
  expected_profile_volume="$(opencli_state_value "$state_file" AGENT_PROFILE_VOLUME)" || return 1
  expected_sentinel="$(opencli_state_value "$state_file" SENTINEL)" || return 1
  [ -n "$expected_project" ] && [ -n "$expected_db_revision" ] && [ -n "$expected_profile_volume" ] && [ -n "$expected_sentinel" ] || return 1

  export COMPOSE_PROJECT_NAME="$expected_project"
  cd "$install_dir" || return 1
  docker info >/dev/null || return 1
  api_id="$(opencli_assert_recovered_container api)" || return 1
  opencli_assert_recovered_container frontend >/dev/null || return 1
  agent_id="$(opencli_assert_recovered_container agent-1)" || return 1

  actual_db_revision="$(docker exec "$api_id" python -c 'import sqlite3; db=sqlite3.connect("file:/data/opencli_admin.db?mode=ro", uri=True); assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"; print(db.execute("SELECT version_num FROM alembic_version").fetchone()[0])')" || return 1
  [ "$actual_db_revision" = "$expected_db_revision" ] || return 1
  [ "$(docker exec "$api_id" python -c 'from pathlib import Path; print(Path("/data/.opencli-host-restart-sentinel").read_text(encoding="utf-8"))')" = "$expected_sentinel" ] || return 1
  opencli_assert_valid_local_auth_state "$api_id" || return 1
  actual_profile_volume="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/home/chrome/.config/chromium"}}{{.Name}}{{end}}{{end}}' "$agent_id")" || return 1
  [ "$actual_profile_volume" = "$expected_profile_volume" ] || return 1
  [ "$(docker exec "$agent_id" sh -c 'cat /home/chrome/.config/chromium/.opencli-host-restart-sentinel')" = "$expected_sentinel" ] || return 1

  # Use the already-running container's environment so neither token appears in
  # terminal output, shell history, nor host process arguments.
  docker exec "$api_id" python -c 'import json, os, urllib.request; request=urllib.request.Request("http://localhost:8000/api/v1/auth/me", headers={"Authorization": f"Bearer {os.environ[\"BOOTSTRAP_ADMIN_TOKEN\"]}", "X-API-Token": os.environ["API_AUTH_TOKEN"]}); payload=json.load(urllib.request.urlopen(request, timeout=5)); assert payload["data"]["subject"] == "bootstrap-admin"' || return 1
  curl -fsS "http://localhost:${FRONTEND_PORT:-3010}/login" >/dev/null || return 1
  curl -fsS "http://localhost:${API_PORT:-8031}/health" >/dev/null || return 1
  echo "Restart recovery verified for project $expected_project: services, database, authentication, and browser profile persisted."
}

opencli_print_restart_status() {
  install_dir="$1"
  frontend_port="$2"
  api_port="$3"
  baseline_ready="$4"

  if opencli_docker_boot_prerequisite_verified; then
    printf '\nRestart prerequisite verified: native Linux uses the default Docker context, DOCKER_HOST is unset, and the Docker systemd unit is enabled.\n'
    printf 'This confirms boot prerequisites only; the installer has not tested a host restart.\n'
  else
    printf '\nRestart recovery unverified. OpenCLI is ready now, but its host-restart recovery has not been tested.\n'
    if opencli_is_wsl; then
      printf 'Action: WSL is development-only for this recovery contract; no production host-restart claim is made.\n'
    else
      case "$(uname -s 2>/dev/null || true)" in
        Linux)
          printf 'Action: use the default Docker context, unset DOCKER_HOST, and, if appropriate, enable Docker yourself with: sudo systemctl enable docker\n'
          ;;
        Darwin)
          printf 'Action: enable "Start Docker Desktop when you sign in" in Docker Desktop settings.\n'
          ;;
        *)
          printf 'Action: configure the Docker daemon to start automatically for this host.\n'
          ;;
      esac
    fi
  fi

  if [ "$baseline_ready" = "1" ]; then
    quoted_dir="$(opencli_shell_quote "$install_dir")"
    quoted_frontend_port="$(opencli_shell_quote "$frontend_port")"
    quoted_api_port="$(opencli_shell_quote "$api_port")"
    printf 'A non-secret pre-restart baseline was saved in %s/%s.\n' "$install_dir" "$OPENCLI_RESTART_STATE_FILE_NAME"
    printf 'After the next host restart, verify without docker compose up/start/restart:\n'
    printf '  cd %s\n' "$quoted_dir"
    printf '  OPENCLI_ADMIN_DIR=%s FRONTEND_PORT=%s API_PORT=%s sh ./scripts/install.sh --verify-restart-recovery\n' "$quoted_dir" "$quoted_frontend_port" "$quoted_api_port"
  else
    printf 'The pre-restart persistence baseline could not be created; recovery remains unverified.\n'
  fi
}
