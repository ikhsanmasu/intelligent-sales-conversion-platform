#!/usr/bin/env bash

# Source this file on server:
#   source deploy.sh
# Then run:
#   deploy_keep_volumes
#   deploy_reset_volumes
#
# You can also execute directly:
#   bash deploy.sh keep
#   bash deploy.sh wipe
#   bash deploy.sh

DEPLOY_COMPOSE_FILE_DEFAULT="docker-compose.server.yml"
DEPLOY_PROJECT_NAME_DEFAULT="iscp-server"

deploy_help() {
  cat <<'EOF'
Deploy helpers loaded.

Commands:
  deploy_keep_volumes [compose_file] [project_name]
    - Recreate services without deleting volumes.
  deploy_reset_volumes [compose_file] [project_name]
    - Recreate services and delete volumes first (fresh DB/data).

Defaults:
  compose_file : docker-compose.server.yml
  project_name : iscp-server

Direct execution:
  bash deploy.sh keep
  bash deploy.sh wipe
  bash deploy.sh
EOF
}

_deploy_require_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "[deploy] docker command not found." >&2
    return 1
  fi
}

_deploy_git_pull() {
  if ! command -v git >/dev/null 2>&1; then
    echo "[deploy] git command not found." >&2
    return 1
  fi

  if [[ ! -d ".git" ]]; then
    echo "[deploy] .git directory not found in current path." >&2
    return 1
  fi

  echo "[deploy] pulling latest changes..."
  git pull --ff-only
}

_deploy_run() {
  local mode="${1:-keep}"
  local compose_file="${2:-$DEPLOY_COMPOSE_FILE_DEFAULT}"
  local project_name="${3:-$DEPLOY_PROJECT_NAME_DEFAULT}"

  _deploy_git_pull || return 1
  _deploy_require_docker || return 1

  if [[ ! -f "$compose_file" ]]; then
    echo "[deploy] compose file not found: $compose_file" >&2
    return 1
  fi

  echo "[deploy] mode=$mode compose=$compose_file project=$project_name"

  if [[ "$mode" == "wipe" ]]; then
    echo "[deploy] stopping stack and deleting volumes..."
    docker compose -p "$project_name" -f "$compose_file" down --volumes --remove-orphans
  else
    echo "[deploy] stopping stack without deleting volumes..."
    docker compose -p "$project_name" -f "$compose_file" down --remove-orphans
  fi

  echo "[deploy] building and starting containers..."
  docker compose -p "$project_name" -f "$compose_file" up -d --build

  echo "[deploy] current status:"
  docker compose -p "$project_name" -f "$compose_file" ps
}

deploy_keep_volumes() {
  local compose_file="${1:-$DEPLOY_COMPOSE_FILE_DEFAULT}"
  local project_name="${2:-$DEPLOY_PROJECT_NAME_DEFAULT}"
  _deploy_run "keep" "$compose_file" "$project_name"
}

deploy_reset_volumes() {
  local compose_file="${1:-$DEPLOY_COMPOSE_FILE_DEFAULT}"
  local project_name="${2:-$DEPLOY_PROJECT_NAME_DEFAULT}"
  _deploy_run "wipe" "$compose_file" "$project_name"
}

_deploy_select_mode_interactive() {
  local choice=""

  while true; do
    cat <<'EOF'
[deploy] Pilih mode deploy:
  A) Keep volumes   (aman, data tetap ada)
  B) Wipe volumes   (hapus volume, data fresh)
EOF
    read -r -p "Masukkan pilihan [A/B]: " choice

    case "${choice^^}" in
      A)
        echo "[deploy] Pilihan A: Keep volumes (data tetap ada)." >&2
        echo "keep"
        return 0
        ;;
      B)
        echo "[deploy] Pilihan B: Wipe volumes (hapus volume, data fresh)." >&2
        echo "wipe"
        return 0
        ;;
      *)
        echo "[deploy] Pilihan tidak valid. Harus A atau B."
        ;;
    esac
  done
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  mode="${1:-}"
  if [[ -z "$mode" ]]; then
    mode="$(_deploy_select_mode_interactive)"
  fi

  case "${mode,,}" in
    keep|a)
      echo "[deploy] Mode KEEP: container di-recreate tanpa menghapus volume."
      deploy_keep_volumes "${2:-$DEPLOY_COMPOSE_FILE_DEFAULT}" "${3:-$DEPLOY_PROJECT_NAME_DEFAULT}"
      ;;
    wipe|b)
      echo "[deploy] Mode WIPE: container di-recreate dan volume dihapus dulu."
      deploy_reset_volumes "${2:-$DEPLOY_COMPOSE_FILE_DEFAULT}" "${3:-$DEPLOY_PROJECT_NAME_DEFAULT}"
      ;;
    help|-h|--help)
      deploy_help
      ;;
    *)
      echo "[deploy] unknown mode: $mode" >&2
      deploy_help
      exit 1
      ;;
  esac
else
  deploy_help
fi
