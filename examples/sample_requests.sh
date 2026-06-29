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

curl -s -X POST "$BASE_URL/submit" \
  -H "Content-Type: application/json" \
  -d '{
    "creator_id": "creator-demo",
    "text": "The lamp above the desk flickered twice before dawn. I left the letter folded under a chipped mug and waited for the hallway to stop echoing."
  }'

curl -s -X POST "$BASE_URL/submit" \
  -H "Content-Type: application/json" \
  -d '{
    "creator_id": "creator-image-demo",
    "content_type": "image_description",
    "image_description": "A hand-painted poster hangs beside a studio window after a rainy afternoon. The paper is buckled at the corners, the lettering is uneven, and a coffee ring cuts through the lower margin near the artist notes."
  }'

curl -s -X POST "$BASE_URL/submit" \
  -H "Content-Type: application/json" \
  -d '{
    "creator_id": "creator-metadata-demo",
    "content_type": "metadata",
    "metadata": {
      "title": "Gallery Wall Notes",
      "caption": "Installation notes for a handmade gallery wall with uneven frames.",
      "materials": ["paper", "ink", "wood"]
    }
  }'

CONTENT_ID="$(curl -s -X POST "$BASE_URL/submit" \
  -H "Content-Type: application/json" \
  -d '{
    "creator_id": "creator-certificate-demo",
    "content": "ok so i finally tried that new ramen place downtown and honestly? underwhelming. the broth was fine but they put WAY too much sodium in it and i was thirsty for like three hours after. my friend got the spicy version and said it was better."
  }' | python -c 'import json, sys; print(json.load(sys.stdin)["content_id"])')"

curl -s -X POST "$BASE_URL/certificate" \
  -H "Content-Type: application/json" \
  -d "{
    \"content_id\": \"$CONTENT_ID\",
    \"creator_id\": \"creator-certificate-demo\",
    \"verification_method\": \"draft_history\",
    \"evidence_summary\": \"Creator provided timestamped draft notes and revision history that match the submitted piece.\"
  }"

curl -s "$BASE_URL/api/analytics"
curl -s -o /dev/null -w "%{http_code}\n" "$BASE_URL/dashboard"
curl -s "$BASE_URL/api/log?limit=3"
