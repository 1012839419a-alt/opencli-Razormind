#!/usr/bin/env bash
set -Eeuo pipefail

image_prefix="${IMAGE_PREFIX:?IMAGE_PREFIX is required}"
candidate_tag="${CANDIDATE_TAG:?CANDIDATE_TAG is required}"
timeout_seconds="${OPENCLI_AGENT_IMAGE_TIMEOUT_SECONDS:-120}"
[[ "$timeout_seconds" =~ ^[1-9][0-9]*$ ]] || { echo "Invalid agent image timeout: $timeout_seconds" >&2; exit 2; }

suffix="${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-0}-$$"
slim_name="opencli-agent-slim-$suffix"
chrome_name="opencli-agent-chrome-$suffix"
slim_ref="$image_prefix/opencli-admin-agent:$candidate_tag"
chrome_ref="$image_prefix/opencli-admin-agent:$candidate_tag-chrome"

cleanup() {
  docker rm -f "$slim_name" "$chrome_name" >/dev/null 2>&1 || true
}
trap cleanup EXIT

wait_for_agent() {
  local name="$1"
  local deadline=$((SECONDS + timeout_seconds))
  while true; do
    if docker exec "$name" curl --fail --silent --show-error http://localhost:19823/health |
      python -c 'import json,sys; payload=json.load(sys.stdin); assert payload["status"] == "ok"; assert payload["opencli_bin_exists"] is True' 2>/dev/null; then
      return 0
    fi
    if [[ "$(docker inspect --format '{{.State.Status}}' "$name" 2>/dev/null || true)" != "running" ]]; then
      docker logs "$name" >&2 || true
      echo "$name exited before its health endpoint became ready." >&2
      return 1
    fi
    if (( SECONDS >= deadline )); then
      docker logs "$name" >&2 || true
      echo "$name did not become ready within $timeout_seconds seconds." >&2
      return 1
    fi
    sleep 2
  done
}

docker pull "$slim_ref"
docker pull "$chrome_ref"
docker run -d --name "$slim_name" -e AGENT_REGISTER=off "$slim_ref" >/dev/null
docker run -d --name "$chrome_name" -e AGENT_REGISTER=off "$chrome_ref" >/dev/null

# Each variant gets its own complete readiness budget.
wait_for_agent "$slim_name"
wait_for_agent "$chrome_name"

docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$slim_name" | grep -Fx 'AGENT_HAS_CHROME=false'
docker exec "$slim_name" sh -c '! command -v chromium >/dev/null 2>&1'
docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$chrome_name" | grep -Fx 'AGENT_HAS_CHROME=true'
docker exec "$chrome_name" sh -c 'command -v chromium >/dev/null && test -s /tmp/browser-runtime-report.json'
docker exec "$chrome_name" curl --fail --silent --show-error http://localhost:9222/json/version >/dev/null

echo "Both candidate agent entrypoints passed: slim stayed browser-free and chrome completed its embedded-browser self-check."
