#!/usr/bin/env bash
# Restart the server, regenerate trace evidence, pull the real cost-log
# breakdown, and print everything needed to finish WRITEUP.md
# deliverables 7/8/9. Assumes you've already dropped the fixed
# src/gateway/router.py into place yourself.
#
# Usage:  bash scripts/finalize.sh
# Run from the repo root (starter/).

set -uo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=.

OUT="FIX-OUTPUT.md"
: > "$OUT"
log()  { echo "$@" | tee -a "$OUT"; }
md()   { echo -e "\n## $*\n" | tee -a "$OUT"; }
code() { echo '```' >> "$OUT"; echo "$1" >> "$OUT"; echo '```' >> "$OUT"; }

SERVER_PID=""
cleanup() {
  if [[ -n "$SERVER_PID" ]]; then
    kill "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# --- Step 1: confirm the fix is actually on disk before we go further.
md "1. Confirm router.py fix is present"
GREP_OUT="$(grep -n 'start_as_current_span' src/gateway/router.py || true)"
echo "$GREP_OUT" | tee -a "$OUT"
if ! echo "$GREP_OUT" | grep -q '"request"'; then
  log "WARNING: router.py does not look patched (no \"request\" span found)."
  log "Fix it before trusting the trace evidence below."
fi

# --- Step 2: restart the server in the background with this file live.
md "2. Restart server"
pkill -f "uvicorn src.gateway.app:app" 2>/dev/null || true
sleep 1
uv run uvicorn src.gateway.app:app --port 8080 > /tmp/serve.log 2>&1 &
SERVER_PID=$!
log "Started server (pid $SERVER_PID), waiting for /health ..."
log "(first boot after a restart loads the guardrail models — can take several minutes, this is normal)"
UP=0
for i in $(seq 1 300); do
  if curl -fs http://localhost:8080/health > /dev/null 2>&1; then
    log "Server is up after ${i}s."
    UP=1
    break
  fi
  sleep 1
done
if [[ "$UP" -eq 0 ]]; then
  log "ERROR: server never came up after 300s. Check /tmp/serve.log:"
  tail -n 30 /tmp/serve.log | tee -a "$OUT"
  exit 1
fi

# --- Step 2.5: clear the semantic cache. It's on-disk and survives a
# server restart, so without this every seed query hits the cache,
# route_query() (and the tracing fix inside it) never runs, and you get
# nothing but empty CreateEmbeddings traces.
md "2.5. Clear semantic cache"
CLEAR_OUT="$(uv run python -c "
import chromadb
client = chromadb.PersistentClient(path='data/chroma')
try:
    client.delete_collection('cache')
    print('cache collection cleared')
except Exception as e:
    print(f'no cache collection to clear ({e})')
" 2>&1)"
echo "$CLEAR_OUT" | tee -a "$OUT"

# --- Step 3: seed + export traces.
md "3. make seed-traces"
SEED_OUT="$(uv run python scripts/seed_traces.py 2>&1)"
echo "$SEED_OUT" | tee -a "$OUT"

md "4. make show-traces"
TRACE_OUT="$(uv run python scripts/show_traces.py 2>&1)"
echo "$TRACE_OUT" >> "$OUT"
code "$TRACE_OUT"

# --- Step 4: cost log evidence.
md "5. Cost log — tail + query_type breakdown"
log "tail -n 5 data/cost_log.jsonl:"
TAIL_OUT="$(tail -n 5 data/cost_log.jsonl 2>&1)"
code "$TAIL_OUT"
log "query_type counts:"
QT_OUT="$(grep -o '"query_type": *"[^"]*"' data/cost_log.jsonl | sort | uniq -c)"
code "$QT_OUT"

# --- Step 5: git identity for the writeup.
md "6. Git branch + last commit"
BRANCH="$(git branch --show-current 2>&1)"
LASTLOG="$(git log --oneline -1 2>&1)"
log "Branch: $BRANCH"
log "Last commit: $LASTLOG"

# --- Step 6: final test/verify since router.py changed.
md "7. make test (final, post-fix)"
TEST_OUT="$(uv run pytest -q 2>&1 | tail -n 20)"
code "$TEST_OUT"

md "8. make verify (final, post-fix)"
VERIFY_OUT="$(uv run python scripts/verify_capstone.py 2>&1 | tail -n 20)"
code "$VERIFY_OUT"

# --- Step 7: stage + commit everything.
md "9. Commit"
# `[[ -d .git ]]` only checks the literal cwd for a .git folder. git
# itself searches upward through parent directories for the repo root,
# which is why `git branch`/`git log` above succeed from this same cwd
# even when .git isn't directly here (it's likely one level up, e.g.
# /workspace/code/.git while this script runs from /workspace/code/starter).
# Use `git rev-parse` — the same upward-search git itself uses — instead
# of a literal directory check.
if git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
  git add -A
  if git diff --cached --quiet; then
    log "Nothing new to commit."
  else
    git commit -m "Fix classification tracing span, refresh trace/cost evidence" >&2 || log "Commit failed — check output above."
  fi
else
  log "Not inside a git working tree — run from your real checkout."
fi

log ""
log "=================================================================="
log "Done. Everything above is also saved to $OUT — paste its contents"
log "back to Claude to get the corrected WRITEUP.md sections."
log "=================================================================="