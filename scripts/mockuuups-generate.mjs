#!/usr/bin/env node
/**
 * Generate device mockups via the Mockuuups MCP server (streamable HTTP).
 *
 * Usage:
 *   MOCKUUUPS_API_KEY=<key> node scripts/mockuuups-generate.mjs list
 *   MOCKUUUPS_API_KEY=<key> node scripts/mockuuups-generate.mjs gen <image-url> [mockup-id]
 *
 * The server is also registered in ~/.kimi-code/mcp.json (user level) so
 * future Kimi Code sessions can call mcp__mockuuups__* directly.
 */

const ENDPOINT = "https://mcp.mockuuups.studio/mcp";
const API_KEY = process.env.MOCKUUUPS_API_KEY;

if (!API_KEY) {
  console.error("Missing MOCKUUUPS_API_KEY env var.");
  process.exit(1);
}

let nextId = 0;
let sessionId = null;

async function rpc(method, params) {
  const id = ++nextId;
  const res = await fetch(ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json, text/event-stream",
      Authorization: `Bearer ${API_KEY}`,
      ...(sessionId ? { "mcp-session-id": sessionId } : {}),
    },
    body: JSON.stringify({ jsonrpc: "2.0", id, method, params }),
  });

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${body.slice(0, 300)}`);
  }

  if (!sessionId && res.headers.get("mcp-session-id")) {
    sessionId = res.headers.get("mcp-session-id");
  }

  const ctype = res.headers.get("content-type") || "";
  if (ctype.includes("text/event-stream")) {
    const text = await res.text();
    for (const line of text.split("\n")) {
      if (line.startsWith("data:")) {
        const msg = JSON.parse(line.slice(5).trim());
        if (msg.id === id) return msg;
      }
    }
    throw new Error("No JSON-RPC response in SSE stream");
  }
  return res.json();
}

async function notify(method, params) {
  await fetch(ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json, text/event-stream",
      Authorization: `Bearer ${API_KEY}`,
      ...(sessionId ? { "mcp-session-id": sessionId } : {}),
    },
    body: JSON.stringify({ jsonrpc: "2.0", method, params }),
  });
}

async function main() {
  const [, , cmd, ...args] = process.argv;

  const init = await rpc("initialize", {
    protocolVersion: "2025-03-26",
    capabilities: {},
    clientInfo: { name: "mtp-marketing", version: "1.0.0" },
  });
  if (init.error) throw new Error(`initialize: ${JSON.stringify(init.error)}`);
  await notify("notifications/initialized", {});

  if (cmd === "list") {
    const tools = await rpc("tools/list", {});
    if (tools.error) throw new Error(JSON.stringify(tools.error));
    for (const t of tools.result.tools) {
      console.log(`\n== ${t.name} ==\n${t.description || ""}`);
      console.log(JSON.stringify(t.inputSchema, null, 2));
    }
    return;
  }

  if (cmd === "gen") {
    const [imageUrl, mockupId] = args;
    if (!imageUrl) {
      console.error("Usage: gen <image-url> [mockup-id]");
      process.exit(1);
    }
    const arguments_ = { image_url: imageUrl };
    if (mockupId) arguments_.mockup_id = mockupId;
    const call = await rpc("tools/call", {
      name: "generate_mockup",
      arguments: arguments_,
    });
    if (call.error) throw new Error(JSON.stringify(call.error));
    console.log(JSON.stringify(call.result, null, 2));
    return;
  }

  console.error(`Unknown command: ${cmd}. Use "list" or "gen".`);
  process.exit(1);
}

main().catch((e) => {
  console.error("FAIL:", e.message);
  process.exit(1);
});
