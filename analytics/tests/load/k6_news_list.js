/**
 * k6 load test — News list endpoint
 *
 * Validates: Requirements 6.3 (100 concurrent users, p99 < 500ms, error rate < 1%)
 *
 * Run:
 *   k6 run tests/load/k6_news_list.js
 *   k6 run tests/load/k6_news_list.js -e BASE_URL=http://localhost:8000 -e AUTH_TOKEN=your_jwt
 */
import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend, Counter } from "k6/metrics";

// Custom metrics
const errorRate    = new Rate("news_list_errors");
const latency      = new Trend("news_list_latency_ms");
const requestCount = new Counter("news_list_requests_total");

export const options = {
  stages: [
    { duration: "10s", target: 20  },  // ramp up to 20 VUs
    { duration: "10s", target: 100 },  // ramp up to 100 VUs
    { duration: "30s", target: 100 },  // sustained load at 100 VUs
    { duration: "10s", target: 0   },  // ramp down
  ],
  thresholds: {
    // Requirement 6.3: p99 < 500ms
    http_req_duration:    ["p(99)<500"],
    // Requirement 6.3: error rate < 1%
    http_req_failed:      ["rate<0.01"],
    news_list_errors:     ["rate<0.01"],
  },
};

const BASE_URL    = __ENV.BASE_URL    || "http://localhost:8000";
const AUTH_TOKEN  = __ENV.AUTH_TOKEN  || "";

// Vary query params to avoid cache saturation
const TICKERS  = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", ""];
const LIMITS   = [10, 20, 50];

function buildHeaders() {
  const headers = { "Content-Type": "application/json" };
  if (AUTH_TOKEN) {
    headers["Authorization"] = `Bearer ${AUTH_TOKEN}`;
  }
  return headers;
}

export default function () {
  const ticker = TICKERS[Math.floor(Math.random() * TICKERS.length)];
  const limit  = LIMITS[Math.floor(Math.random() * LIMITS.length)];

  let url = `${BASE_URL}/api/v1/news?limit=${limit}`;
  if (ticker) {
    url += `&ticker=${ticker}`;
  }

  const res = http.get(url, {
    headers: buildHeaders(),
    tags: { endpoint: "news_list" },
  });

  const ok = check(res, {
    "status 200":          (r) => r.status === 200,
    "has items array":     (r) => {
      try {
        const body = r.json();
        return Array.isArray(body.items) || Array.isArray(body);
      } catch {
        return false;
      }
    },
    "latency < 500ms":     (r) => r.timings.duration < 500,
    "not rate limited":    (r) => r.status !== 429,
  });

  errorRate.add(!ok);
  latency.add(res.timings.duration);
  requestCount.add(1);

  // Small think time — realistic user pacing
  sleep(0.3);
}

export function handleSummary(data) {
  const p99 = data.metrics.http_req_duration
    ? data.metrics.http_req_duration.values["p(99)"]
    : "N/A";
  const errRate = data.metrics.http_req_failed
    ? (data.metrics.http_req_failed.values.rate * 100).toFixed(2)
    : "N/A";

  console.log("\n=== News List Load Test Summary ===");
  console.log(`  p99 latency : ${typeof p99 === "number" ? p99.toFixed(1) + "ms" : p99}`);
  console.log(`  Error rate  : ${errRate}%`);
  console.log(`  Threshold   : p99 < 500ms, errors < 1%`);
  console.log("===================================\n");

  return {
    stdout: JSON.stringify(data, null, 2),
  };
}
