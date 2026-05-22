#!/usr/bin/env bash
# ============================================================
# Analytics Microservice — SDK Generation
# Requires: openapi-generator-cli (npm install -g @openapitools/openapi-generator-cli)
#           or: docker run openapitools/openapi-generator-cli
# ============================================================
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
OUT_DIR="$(dirname "$0")/../sdk"

echo "📥 Fetching OpenAPI schema from $API_URL/openapi.json..."
curl -s "$API_URL/openapi.json" -o /tmp/analytics-openapi.json

echo "🐍 Generating Python SDK..."
openapi-generator-cli generate \
  -i /tmp/analytics-openapi.json \
  -g python \
  -o "$OUT_DIR/python" \
  --additional-properties=packageName=analytics_api_client,projectName=analytics-api-client,packageVersion=1.0.0

echo "📦 Generating TypeScript/Axios SDK..."
openapi-generator-cli generate \
  -i /tmp/analytics-openapi.json \
  -g typescript-axios \
  -o "$OUT_DIR/typescript" \
  --additional-properties=npmName=@quantdinger/analytics-client,npmVersion=1.0.0,supportsES6=true

echo "✅ SDKs generated in $OUT_DIR/"
echo ""
echo "To install Python SDK:"
echo "  pip install -e $OUT_DIR/python"
echo ""
echo "To install TypeScript SDK:"
echo "  cd $OUT_DIR/typescript && npm install && npm run build"
