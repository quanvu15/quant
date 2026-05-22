/**
 * k6 load test — Health endpoint baseline
 * Target: 100 concurrent users, p99 < 200ms
 *
 * Run: k6 run tests/load/k6_health.js
 */
import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

const errorRate = new Rate("errors");
const latency = new Trend("latency_ms");

export const options = {
  stages: [
    { duration: "30s", target: 20 },   // ramp up
    { duration: "1m",  target: 100 },  // sustained load
    { duration: "30s", target: 0 },    // ramp down
  ],
  thresholds: {
    http_req_duration: ["p(99)<200"],   // 99th percentile < 200ms
    http_req_failed:   ["rate<0.01"],   // < 1% errors
    errors:            ["rate<0.01"],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";

export default function () {
  const res = http.get(`${BASE_URL}/health`);

  const ok = check(res, {
    "status 200":        (r) => r.status === 200,
    "status ok":         (r) => r.json("status") === "ok",
    "has version":       (r) => r.json("version") !== undefined,
    "latency < 500ms":   (r) => r.timings.duration < 500,
  });

  errorRate.add(!ok);
  latency.add(res.timings.duration);

  sleep(0.1);
}
