/**
 * k6 load test — Market data endpoints (cache-heavy)
 * Target: 100 concurrent users, p99 < 2s
 *
 * Run: k6 run tests/load/k6_market_data.js -e API_KEY=fincept_free_xxx
 */
import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

const errorRate = new Rate("errors");
const cacheHitLatency = new Trend("cache_hit_latency_ms");
const cacheMissLatency = new Trend("cache_miss_latency_ms");

export const options = {
  stages: [
    { duration: "30s", target: 10 },
    { duration: "2m",  target: 100 },
    { duration: "30s", target: 0 },
  ],
  thresholds: {
    http_req_duration: ["p(99)<2000"],
    http_req_failed:   ["rate<0.05"],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const API_KEY  = __ENV.API_KEY  || "fincept_admin_test_key";

const SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "BRK-B", "JPM", "V"];

const HEADERS = {
  "X-API-Key": API_KEY,
  "Content-Type": "application/json",
};

export default function () {
  const symbol = SYMBOLS[Math.floor(Math.random() * SYMBOLS.length)];

  // Test 1: Quote (TTL 5s — mix of cache hits/misses)
  const quoteRes = http.get(`${BASE_URL}/api/v1/market/quote/${symbol}`, { headers: HEADERS });
  const quoteOk = check(quoteRes, {
    "quote status 200": (r) => r.status === 200,
  });
  errorRate.add(!quoteOk);
  if (quoteRes.headers["X-Cache"] === "HIT") {
    cacheHitLatency.add(quoteRes.timings.duration);
  } else {
    cacheMissLatency.add(quoteRes.timings.duration);
  }

  sleep(0.05);

  // Test 2: Equity info (TTL 1h — mostly cache hits after warmup)
  const infoRes = http.get(`${BASE_URL}/api/v1/equity/${symbol}/info`, { headers: HEADERS });
  check(infoRes, { "info status 200": (r) => r.status === 200 });

  sleep(0.05);

  // Test 3: Technical indicators (TTL 60s)
  const techRes = http.post(
    `${BASE_URL}/api/v1/technical/indicators`,
    JSON.stringify({ symbol, indicators: ["RSI", "MACD"] }),
    { headers: HEADERS }
  );
  check(techRes, { "tech status 200": (r) => r.status === 200 });

  sleep(0.1);
}
