ls -la data/inbox/failed/
cat data/inbox/failed/*.error.txt 2>/dev/null

curl -s -X POST http://localhost:8080/query -H 'Content-Type: application/json' \
  -d '{"question": "Tell me about the Engage Pursuit MX Lite paddle with the ControlPro polymer core"}' | uv run python -m json.tool