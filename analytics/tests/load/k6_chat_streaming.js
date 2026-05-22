/**
 * k6 load test — Chat completions SSE streaming endpoint
 *
 * Validates: Requirements 6.3 (50 concurrent SSE streams, TTFB < 1500ms p95, no connection drops)
 *
 * Each VU:
 *   1. POST /api/v1/chat/completions with stream=true
 *   2. Measures Time-To-First-Byte (TTFB)
 *   3. Reads the full SSE stream until [DONE]
 *   4. Verifies no connection drops
 *
 * Note: Requires a running LLM backend. If no LLM is configured, the test
 * validates that the server responds gracefully (400/503) rather than dropping
 * the connection. Set LLM_BASE_URL + LLM_API_KEY + LLM_MODEL for real streaming.
 *
 * Run:
 *   # Without LLM (validates graceful error handling):
 *   k6 run tests/load/k6_chat_streaming.js
 *
 *   # With LLM (validates real streaming):
 *   k6 run tests/load/k6_chat_streaming.js \
 *     -e LLM_BASE_URL=https://api.openai.com/v1 \
 *     -e LLM_API_KEY=sk-xxx \
 *     -e LLM_MODEL=gpt-4o-mini \
 *     -e AUTH_TOKEN=your_jwt
 */
import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend, Counter } from "k6/metrics";

// Custom metrics
const errorRate        = new Rate("chat_stream_errors");
const ttfb             = new Trend("chat_stream_ttfb_ms");
const streamDuration   = new Trend("chat_stream_total_ms");
const connectionDrops  = new Counter("chat_stream_connection_drops");
const chunksReceived   = new Counter("chat_stream_chunks_total");

export const options = {
  stages: [
    { duration: "10s", target: 10 },  // ramp up
    { duration: "10s", target: 50 },  // ramp up to 50 VUs
    { duration: "60s", target: 50 },  // sustained 50 concurrent SSE streams
    { duration: "10s", target: 0  },  // ramp down
  ],
  thresholds: {
    // Requirement 6.3: TTFB < 1500ms p95
    chat_stream_ttfb_ms:       ["p(95)<1500"],
    // Requirement 6.3: no connection drops
    chat_stream_connection_drops: ["count<1"],
    // Overall error rate (graceful errors like 400/503 are OK, drops are not)
    chat_stream_errors:        ["rate<0.05"],
  },
};

const BASE_URL     = __ENV.BASE_URL     || "http://localhost:8000";
const AUTH_TOKEN   = __ENV.AUTH_TOKEN   || "";
const LLM_BASE_URL = __ENV.LLM_BASE_URL || "";
const LLM_API_KEY  = __ENV.LLM_API_KEY  || "";
const LLM_MODEL    = __ENV.LLM_MODEL    || "gpt-4o-mini";

// Varied prompts to avoid identical request caching
const PROMPTS = [
  "What is the current market sentiment for tech stocks?",
  "Briefly explain the concept of P/E ratio.",
  "What are the key risks in the current macro environment?",
  "Summarize the difference between growth and value investing.",
  "What is dollar-cost averaging?",
];

function buildHeaders() {
  const headers = { "Content-Type": "application/json" };
  if (AUTH_TOKEN) {
    headers["Authorization"] = `Bearer ${AUTH_TOKEN}`;
  }
  return headers;
}

function buildPayload() {
  const prompt = PROMPTS[Math.floor(Math.random() * PROMPTS.length)];

  const payload = {
    messages: [
      { role: "user", content: prompt },
    ],
    stream: true,
    max_tokens: 128,  // keep responses short for load test
  };

  // Attach LLM config if provided via env
  if (LLM_BASE_URL && LLM_API_KEY) {
    payload.llm_config = {
      model:    LLM_MODEL,
      base_url: LLM_BASE_URL,
      api_key:  LLM_API_KEY,
    };
  }

  return JSON.stringify(payload);
}

export default function () {
  const startTime = Date.now();
  let firstByteReceived = false;
  let streamCompleted   = false;
  let chunkCount        = 0;

  const res = http.post(
    `${BASE_URL}/api/v1/chat/completions`,
    buildPayload(),
    {
      headers: buildHeaders(),
      tags:    { endpoint: "chat_completions_stream" },
      // Allow enough time for streaming to complete
      timeout: "90s",
      // k6 reads the full response body — for SSE this means the complete stream
    }
  );

  const elapsed = Date.now() - startTime;

  // TTFB: k6 provides this via timings.waiting (time until first byte)
  const ttfbMs = res.timings.waiting;
  ttfb.add(ttfbMs);
  streamDuration.add(elapsed);

  // Determine if this was a streaming response or a graceful error
  const isStreaming = res.status === 200;
  const isGracefulError = [400, 422, 503].includes(res.status);
  const isConnectionDrop = res.status === 0 || res.status >= 500 && !isGracefulError;

  if (isConnectionDrop) {
    connectionDrops.add(1);
  }

  if (isStreaming) {
    firstByteReceived = true;

    // Parse SSE chunks from the response body
    const body = res.body || "";
    const lines = body.split("\n");
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const data = line.slice(6).trim();
        if (data === "[DONE]") {
          streamCompleted = true;
        } else if (data) {
          chunkCount++;
          chunksReceived.add(1);
        }
      }
    }
  }

  const ok = check(res, {
    "no connection drop":    () => !isConnectionDrop,
    "TTFB < 1500ms":         () => ttfbMs < 1500,
    "valid response status": (r) => isStreaming || isGracefulError,
  });

  if (isStreaming) {
    check(res, {
      "stream has chunks":   () => chunkCount > 0,
      "stream completed":    () => streamCompleted,
    });
  }

  errorRate.add(isConnectionDrop);

  // Think time between requests — SSE streams are long-lived so keep it short
  sleep(0.5);
}

export function handleSummary(data) {
  const p95ttfb = data.metrics.chat_stream_ttfb_ms
    ? data.metrics.chat_stream_ttfb_ms.values["p(95)"]
    : "N/A";
  const drops = data.metrics.chat_stream_connection_drops
    ? data.metrics.chat_stream_connection_drops.values.count
    : 0;
  const totalChunks = data.metrics.chat_stream_chunks_total
    ? data.metrics.chat_stream_chunks_total.values.count
    : 0;

  console.log("\n=== Chat Streaming Load Test Summary ===");
  console.log(`  TTFB p95          : ${typeof p95ttfb === "number" ? p95ttfb.toFixed(1) + "ms" : p95ttfb}`);
  console.log(`  Connection drops  : ${drops}`);
  console.log(`  SSE chunks total  : ${totalChunks}`);
  console.log(`  Thresholds        : TTFB p95 < 1500ms, drops = 0`);
  console.log("========================================\n");

  return {
    stdout: JSON.stringify(data, null, 2),
  };
}
