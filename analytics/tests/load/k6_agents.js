/**
 * k6 load test — AI Agents endpoints (rate-limited, expensive)
 * Target: 10 concurrent users (agent endpoints are rate-limited to 10/min)
 *
 * Run: k6 run tests/load/k6_agents.js -e API_KEY=xxx -e LLM_KEY=sk-xxx
 */
import http from "k6/http";
import { check, sleep } from "k6";
import { Rate } from "k6/metrics";

const errorRate = new Rate("errors");

export const options = {
  stages: [
    { duration: "30s", target: 5 },
    { duration: "2m",  target: 10 },
    { duration: "30s", target: 0 },
  ],
  thresholds: {
    http_req_duration: ["p(95)<30000"],  // agents can take up to 30s
    http_req_failed:   ["rate<0.1"],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const API_KEY  = __ENV.API_KEY  || "fincept_admin_test_key";
const LLM_KEY  = __ENV.LLM_KEY  || "";

const HEADERS = {
  "X-API-Key": API_KEY,
  "Content-Type": "application/json",
};

const LLM_CONFIG = {
  model: "gpt-4o-mini",
  api_key: LLM_KEY,
  base_url: "https://api.openai.com/v1",
  temperature: 0.3,
  max_tokens: 512,
};

export default function () {
  // Test: Agent discovery (public, cached)
  const discoverRes = http.get(`${BASE_URL}/api/v1/agents/`, { headers: HEADERS });
  check(discoverRes, { "discover 200": (r) => r.status === 200 });

  sleep(1);

  // Test: Agent run (requires real LLM key — skip if not set)
  if (LLM_KEY) {
    const runRes = http.post(
      `${BASE_URL}/api/v1/agents/run`,
      JSON.stringify({
        query: "What is the current market sentiment?",
        llm_config: LLM_CONFIG,
      }),
      { headers: HEADERS, timeout: "30s" }
    );
    const runOk = check(runRes, {
      "run 200": (r) => r.status === 200,
      "run success": (r) => {
        try { return r.json("success") === true; } catch { return false; }
      },
    });
    errorRate.add(!runOk);
  }

  sleep(5); // respect rate limits
}
