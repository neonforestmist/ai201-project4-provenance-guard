#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:5000}"

curl -s "$BASE_URL/health"

curl -s -X POST "$BASE_URL/api/submissions" \
  -H "Content-Type: application/json" \
  -d '{
    "creator_id": "creator-demo",
    "content": "In today'\''s rapidly evolving creative landscape, it is important to note that storytelling empowers communities. Overall, this essay explores how technology can enhance expression, foster collaboration, and unlock new opportunities for meaningful human connection."
  }'

curl -s "$BASE_URL/api/log?limit=3"

