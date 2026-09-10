#!/usr/bin/env node
/**
 * Mockuuups Studio API client (direct REST).
 *
 * NOTE: the hosted MCP gateway (https://mcp.mockuuups.studio/mcp) currently
 * rejects valid developer API keys ("Invalid token format"), so this client
 * calls the underlying Studio REST API directly — same renders, same catalog.
 *
 * Usage:
 *   MOCKUUUPS_API_KEY=<key> node scripts/mockuuups-generate.mjs list [page]
 *     Browse the mockup catalog (50 per page).
 *   MOCKUUUPS_API_KEY=<key> node scripts/mockuuups-generate.mjs render <mockup-id> <image-url> [size]
 *     Render an image into a mockup. Returns JPEG bytes on stdout.
 *     Free plan caps `size` at 1000 (longest side); larger requests fail
 *     with feature-not-available / "hires".
 *
 * Image hosting gotcha: the render farm fetches contents[].url through
 * assets.mockuuups.com/image-proxy/ — some hosts (catbox.moe) are blocked.
 * uguu.se URLs work. Hosts must be publicly reachable.
 */

const ENDPOINT = "https://api.mockuuups.studio/v1";
const API_KEY = process.env.MOCKUUUPS_API_KEY;

if (!API_KEY) {
  console.error("Missing MOCKUUUPS_API_KEY env var.");
  process.exit(1);
}

async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(`${ENDPOINT}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${API_KEY}`,
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text.slice(0, 300)}`);
  }
  const ctype = res.headers.get("content-type") || "";
  return ctype.includes("application/json") ? res.json() : Buffer.from(await res.arrayBuffer());
}

async function main() {
  const [, , cmd, ...args] = process.argv;

  if (cmd === "list") {
    const page = args[0] || 1;
    const data = await api(`/mockups?page=${page}`);
    console.log(`total: ${data.total}, page ${page}`);
    for (const m of data.mockups || []) {
      const pl = (m.placements || [])[0] || {};
      console.log(`${m.id} | ${pl.family || "?"} | ${m.width}x${m.height} | ${m.title}`);
    }
    return;
  }

  if (cmd === "render") {
    const [mockupId, imageUrl, size = "1000"] = args;
    if (!mockupId || !imageUrl) {
      console.error("Usage: render <mockup-id> <image-url> [size]");
      process.exit(1);
    }
    const image = await api("/renders", {
      method: "POST",
      body: {
        mockup: mockupId,
        size: Number(size),
        contents: [{ type: "image", url: imageUrl }],
      },
    });
    process.stdout.write(image);
    return;
  }

  console.error(`Unknown command: ${cmd}. Use "list" or "render".`);
  process.exit(1);
}

main().catch((e) => {
  console.error("FAIL:", e.message);
  process.exit(1);
});
