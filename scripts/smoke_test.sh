#!/usr/bin/env bash
# End-to-end smoke test: runs ingestion against mock server, then hits /suggest.
# Requires: uvicorn, python, curl, jq
# Usage: bash scripts/smoke_test.sh

set -euo pipefail

BACKEND_PORT=8000
MOCK_PORT=9000

echo "=== Zendesk Workflow Suggestion Engine — Smoke Test ==="
echo

# --- Start mock Zendesk server ---
echo "[1/5] Starting mock Zendesk server on port $MOCK_PORT..."
ZENDESK_BASE_URL="http://localhost:$MOCK_PORT" \
  uvicorn scripts.mock_zendesk_server:app --port "$MOCK_PORT" --log-level error &
MOCK_PID=$!
sleep 2
echo "      Mock server PID: $MOCK_PID"

# --- Run ingestion against mock ---
echo "[2/5] Running ingestion against mock Zendesk..."
ZENDESK_BASE_URL="http://localhost:$MOCK_PORT" python scripts/run_ingestion.py
echo "      Ingestion done."

# --- Start backend ---
echo "[3/5] Starting FastAPI backend on port $BACKEND_PORT..."
uvicorn backend.main:app --port "$BACKEND_PORT" --log-level error &
BACKEND_PID=$!
sleep 2
echo "      Backend PID: $BACKEND_PID"

# Cleanup on exit
cleanup() {
  echo
  echo "[cleanup] Stopping servers..."
  kill "$MOCK_PID" "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT

# --- Health check ---
echo "[4/5] Health check..."
HEALTH=$(curl -sf "http://localhost:$BACKEND_PORT/health")
echo "      $HEALTH"
STATUS=$(echo "$HEALTH" | python -c "import sys,json; print(json.load(sys.stdin)['status'])")
if [ "$STATUS" != "ok" ]; then
  echo "FAIL: health check returned status=$STATUS"
  exit 1
fi
echo "      Health check PASSED"

# --- Suggest endpoint ---
echo "[5/5] Testing /suggest with a workflow question..."
RESPONSE=$(curl -sf -X POST "http://localhost:$BACKEND_PORT/suggest" \
  -H "Content-Type: application/json" \
  -d '{
    "ticket_id": "101",
    "current_message": "How do I submit a PTO request for a half day?",
    "ticket_tags": ["workflow-question"]
  }')

echo "      Response: $RESPONSE"

IS_WORKFLOW=$(echo "$RESPONSE" | python -c "import sys,json; print(json.load(sys.stdin)['is_workflow_question'])")
SUGGESTION=$(echo "$RESPONSE" | python -c "import sys,json; r=json.load(sys.stdin); print(r.get('suggestion') or '')")

if [ "$IS_WORKFLOW" != "True" ]; then
  echo "FAIL: is_workflow_question should be True, got $IS_WORKFLOW"
  exit 1
fi

if [ -z "$SUGGESTION" ]; then
  echo "FAIL: suggestion is empty"
  exit 1
fi

echo
echo "=============================="
echo "SMOKE TEST PASSED"
echo "Suggestion: ${SUGGESTION:0:100}..."
echo "=============================="
