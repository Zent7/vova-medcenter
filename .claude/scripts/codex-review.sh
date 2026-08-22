#!/usr/bin/env bash
# codex-review.sh — run an OpenAI Codex CLI code review non-interactively.
#
# Usage:
#   .claude/scripts/codex-review.sh --out <dir> [--prompt <text>] <target-flags...>
#
# Target flags are passed straight to `codex exec review`:
#   --uncommitted            staged + unstaged + untracked changes
#   --base <branch>          everything this branch adds on top of <branch>
#   --commit <sha>           a single commit
#
# Env:
#   CODEX_BIN            explicit path to codex(.exe); skips discovery
#   CODEX_REVIEW_MODEL   model passed as `-m`; otherwise Codex's configured default
#
# Writes into <dir>: review.md (final report), events.jsonl (JSONL event stream),
# codex.log (stderr). Prints the run directory on stdout.
# Exit: 0 review completed, 2 review ran but reported a failed turn, 127 codex not found.

set -uo pipefail

log() { printf '%s\n' "$*" >&2; }

# Highest-versioned codex binary among PATH and the known install locations.
# The Codex desktop app keeps several builds under bin/<hash>/, and an older
# launcher in bin/ can reject the model the newer one is configured to use.
find_codex() {
  if [ -n "${CODEX_BIN:-}" ]; then
    [ -x "$CODEX_BIN" ] && { printf '%s\n' "$CODEX_BIN"; return 0; }
    log "CODEX_BIN=$CODEX_BIN is not executable"; return 1
  fi

  local -a candidates=()
  local p
  p="$(command -v codex 2>/dev/null)" && candidates+=("$p")

  local -a roots=()
  if [ -n "${LOCALAPPDATA:-}" ]; then
    roots+=("$(cygpath -u "$LOCALAPPDATA" 2>/dev/null || printf '%s' "$LOCALAPPDATA")")
  fi
  roots+=("$HOME/AppData/Local" "$HOME/.local/share" "$HOME/.codex")

  local r
  for r in "${roots[@]}"; do
    for p in "$r"/OpenAI/Codex/bin/codex.exe "$r"/OpenAI/Codex/bin/*/codex.exe "$r"/bin/codex; do
      [ -x "$p" ] && candidates+=("$p")
    done
  done
  for p in /usr/local/bin/codex /opt/homebrew/bin/codex; do
    [ -x "$p" ] && candidates+=("$p")
  done

  [ "${#candidates[@]}" -gt 0 ] || { log "codex CLI not found"; return 1; }

  local best="" best_ver="0" ver
  for p in "${candidates[@]}"; do
    ver="$("$p" --version 2>/dev/null | head -1 | grep -oE '[0-9]+(\.[0-9]+)+' | head -1)"
    [ -n "$ver" ] || continue
    if [ "$(printf '%s\n%s\n' "$best_ver" "$ver" | sort -V | tail -1)" = "$ver" ]; then
      best="$p"; best_ver="$ver"
    fi
  done
  [ -n "$best" ] || best="${candidates[0]}"
  log "codex: $best ($best_ver)"
  printf '%s\n' "$best"
}

OUT=""
PROMPT=""
declare -a ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --out)    OUT="${2:-}"; shift 2 ;;
    --prompt) PROMPT="${2:-}"; shift 2 ;;
    *)        ARGS+=("$1"); shift ;;
  esac
done

[ -n "$OUT" ] || OUT="${TMPDIR:-/tmp}/codex-review-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT" || exit 1

CODEX="$(find_codex)" || exit 127

run() {
  local -a cmd=("$CODEX" exec review --json -o "$OUT/review.md")
  [ -n "${1:-}" ] && cmd+=(-m "$1")
  [ "${#ARGS[@]}" -gt 0 ] && cmd+=("${ARGS[@]}")
  [ -n "$PROMPT" ] && cmd+=("$PROMPT")
  log "run: ${cmd[*]}"
  "${cmd[@]}" > "$OUT/events.jsonl" 2> "$OUT/codex.log"
}

run "${CODEX_REVIEW_MODEL:-}"

# An out-of-date launcher rejects a newer configured model; retry once on a
# model every published CLI build accepts.
if grep -q '"type":"turn.failed"' "$OUT/events.jsonl" 2>/dev/null &&
   grep -qi 'requires a newer version of Codex' "$OUT/events.jsonl"; then
  log "configured model rejected by this codex build; retrying with gpt-5.5"
  mv "$OUT/events.jsonl" "$OUT/events.first-attempt.jsonl"
  run "gpt-5.5"
fi

printf '%s\n' "$OUT"
grep -q '"type":"turn.failed"' "$OUT/events.jsonl" 2>/dev/null && exit 2
exit 0
