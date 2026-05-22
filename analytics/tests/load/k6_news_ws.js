/**
 * k6 load test — News WebSocket endpoint
 *
 * Validates: Requirements 6.3 (200 concurrent WS subscribers, connection success > 99%)
 *
 * Each VU:
 *   1. Connects to ws://localhost:8000/ws/news
 *   2. Waits to receive 3 messages (or times out after 30s)
 *   3. Disconnects cleanly
 *
 * Run:
 *   k6 run tests/load/k6_news_ws.js
 *   k6 run tests/load/k6_news_ws.js -e BASE_URL=http://localhost:8000 -e AUTH_TOKEN=your_jwt
 */
import ws from "k6/ws";
import { check, sleep } from "k6";
import { Rate, Counter, Trend } from "k6/metrics";

// Custom metrics
const connectSuccessRate = new Rate("ws_connect_success");
const connectFailRate    = new Rate("ws_connect_fail");
const messagesReceived   = new Counter("ws_messages_received");
const connectionDuration = new Trend("ws_connection_duration_ms");
const timeToFirstMessage = new Trend("ws_time_to_first_message_ms");

export const options = {
  stages: [
    { duration: "15s", target: 50  },  // ramp up
    { duration: "15s", target: 200 },  // ramp up to 200 VUs
    { duration: "60s", target: 200 },  // sustained 200 concurrent WS connections
    { duration: "10s", target: 0   },  // ramp down
  ],
  thresholds: {
    // Requirement 6.3: connection success rate > 99%
    ws_connect_success:  ["rate>0.99"],
    ws_connect_fail:     ["rate<0.01"],
    // Connections should not error out
    ws_session_duration: ["p(95)<65000"],  // sessions should complete within 65s
  },
};

const BASE_URL   = __ENV.BASE_URL   || "http://localhost:8000";
const AUTH_TOKEN = __ENV.AUTH_TOKEN || "";

// Convert http(s) base URL to ws(s)
function toWsUrl(baseUrl) {
  return baseUrl.replace(/^https:\/\//, "wss://").replace(/^http:\/\//, "ws://");
}

// Optionally filter by ticker to simulate realistic usage
const TICKERS = ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA", ""];  // "" = all news

export default function () {
  const ticker  = TICKERS[Math.floor(Math.random() * TICKERS.length)];
  const wsBase  = toWsUrl(BASE_URL);
  const wsUrl   = ticker
    ? `${wsBase}/ws/news?ticker=${ticker}`
    : `${wsBase}/ws/news`;

  const params = {};
  if (AUTH_TOKEN) {
    // k6 WS supports headers via params
    params.headers = { Authorization: `Bearer ${AUTH_TOKEN}` };
  }

  let connected        = false;
  let msgCount         = 0;
  const TARGET_MSGS    = 3;
  const startTime      = Date.now();
  let firstMsgTime     = null;

  const res = ws.connect(wsUrl, params, function (socket) {
    connected = true;
    connectSuccessRate.add(true);
    connectFailRate.add(false);

    socket.on("open", function () {
      // Connection established — nothing to send, just listen
    });

    socket.on("message", function (data) {
      messagesReceived.add(1);
      msgCount++;

      if (msgCount === 1) {
        firstMsgTime = Date.now() - startTime;
        timeToFirstMessage.add(firstMsgTime);
      }

      // Validate message structure
      try {
        const msg = JSON.parse(data);
        check(msg, {
          "message has type field": (m) => typeof m.type === "string",
          "message type is valid":  (m) =>
            ["article_new", "heartbeat", "backfill", "connected"].includes(m.type),
        });
      } catch {
        // Non-JSON messages (e.g. ping frames) are acceptable
      }

      // Disconnect after receiving TARGET_MSGS messages
      if (msgCount >= TARGET_MSGS) {
        socket.close();
      }
    });

    socket.on("ping", function () {
      // k6 handles pong automatically
    });

    socket.on("error", function (e) {
      console.error(`WS error: ${e.error()}`);
    });

    socket.on("close", function () {
      connectionDuration.add(Date.now() - startTime);
    });

    // Timeout: disconnect after 30s even if we haven't received TARGET_MSGS
    socket.setTimeout(function () {
      socket.close();
    }, 30000);
  });

  if (!connected) {
    connectSuccessRate.add(false);
    connectFailRate.add(true);
  }

  check(res, {
    "WS connection established": () => connected,
    "received messages":         () => msgCount > 0,
  });

  sleep(0.1);
}

export function handleSummary(data) {
  const successRate = data.metrics.ws_connect_success
    ? (data.metrics.ws_connect_success.values.rate * 100).toFixed(2)
    : "N/A";
  const totalMsgs = data.metrics.ws_messages_received
    ? data.metrics.ws_messages_received.values.count
    : 0;

  console.log("\n=== News WebSocket Load Test Summary ===");
  console.log(`  Connection success rate : ${successRate}%`);
  console.log(`  Total messages received : ${totalMsgs}`);
  console.log(`  Threshold               : success rate > 99%`);
  console.log("========================================\n");

  return {
    stdout: JSON.stringify(data, null, 2),
  };
}
