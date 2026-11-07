#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(dirname "$WORKSPACE")"
PYTHON="$WORKSPACE/.venv/bin/python"
PYTHON_DOWNLOAD_URL="https://www.python.org/downloads/macos/"
HOMEBREW_INSTALL_URL="https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh"

if [ "${1:-}" = "--check" ]; then
  echo "START_WORKFLOW.command OK"
  exit 0
fi

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  cat <<'EOF'
Local AI video workflow

Usage:
  ./START_WORKFLOW.command
  ./START_WORKFLOW.command --check
  ./START_WORKFLOW.command --help
  ./START_WORKFLOW.command --no-browser
  ./START_WORKFLOW.command --show-download-settings
  ./START_WORKFLOW.command --set-hf-endpoint https://huggingface.co
  ./START_WORKFLOW.command --set-pip-index https://pypi.org/simple
  ./START_WORKFLOW.command --set-proxy http://127.0.0.1:7890
  ./START_WORKFLOW.command --clear-download-settings

Beginner path: start the frontend, open Environment detection, click one-click setup, then run the generation smoke test.
EOF
  exit 0
fi

python_supported() {
  "$1" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if (3, 10) <= sys.version_info[:2] <= (3, 12) else 1)
PY
}

load_homebrew_path() {
  for brew_bin in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    if [ -x "$brew_bin" ]; then
      eval "$("$brew_bin" shellenv)" || true
      return 0
    fi
  done
  return 1
}

find_python() {
  if [ -x "$WORKSPACE/.venv/bin/python" ] && python_supported "$WORKSPACE/.venv/bin/python"; then
    printf '%s\n' "$WORKSPACE/.venv/bin/python"
    return
  fi
  for name in python3.12 python3.11 python3.10 python3; do
    candidate="$(command -v "$name" || true)"
    if [ -n "$candidate" ] && python_supported "$candidate"; then
      printf '%s\n' "$candidate"
      return
    fi
  done
  for candidate in \
    /opt/homebrew/bin/python3.12 \
    /opt/homebrew/bin/python3.11 \
    /opt/homebrew/bin/python3.10 \
    /usr/local/bin/python3.12 \
    /usr/local/bin/python3.11 \
    /usr/local/bin/python3.10 \
    /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 \
    /Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11 \
    /Library/Frameworks/Python.framework/Versions/3.10/bin/python3.10; do
    if [ -x "$candidate" ] && python_supported "$candidate"; then
      printf '%s\n' "$candidate"
      return
    fi
  done
}

load_homebrew_path || true
PYTHON="$(find_python || true)"

if [ -z "${PYTHON:-}" ]; then
  if command -v brew >/dev/null 2>&1; then
    printf "Python 3.10-3.12 was not found. Install python@3.12 with Homebrew? [y/N] "
    read -r answer
    case "$answer" in
      y|Y|yes|YES)
        brew install python@3.12
        hash -r || true
        PYTHON="$(find_python || true)"
        ;;
    esac
  elif command -v curl >/dev/null 2>&1 && [ -x /bin/bash ]; then
    printf "Python and Homebrew were not found. Install Homebrew now so this launcher can install Python? [y/N] "
    read -r answer
    case "$answer" in
      y|Y|yes|YES)
        echo "Homebrew may ask for your macOS password and Command Line Tools permission."
        /bin/bash -c "$(curl -fsSL "$HOMEBREW_INSTALL_URL")"
        load_homebrew_path || true
        if command -v brew >/dev/null 2>&1; then
          brew install python@3.12
          hash -r || true
          PYTHON="$(find_python || true)"
        fi
        ;;
    esac
  elif command -v open >/dev/null 2>&1; then
    printf "Python 3.10-3.12 was not found. Open the official Python macOS download page? [Y/n] "
    read -r answer
    case "$answer" in
      n|N|no|NO) ;;
      *) open "$PYTHON_DOWNLOAD_URL" ;;
    esac
  fi
fi

if [ -z "${PYTHON:-}" ]; then
  echo "Python 3.10-3.12 is required."
  echo "Install Python 3.10-3.12 from python.org or Homebrew, then run this file again."
  echo "Python macOS download page: $PYTHON_DOWNLOAD_URL"
  echo "Homebrew option: brew install python@3.12"
  echo "If this file is not executable after download, run: bash ./START_WORKFLOW.command"
  exit 1
fi

cd "$WORKSPACE"
exec "$PYTHON" "$WORKSPACE/START_WORKFLOW.py" "$@"
