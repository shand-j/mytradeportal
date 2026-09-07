/**
 * Minimal camelCase <-> snake_case converters for the API boundary. The backend
 * speaks snake_case; the app speaks camelCase. Kept dependency-free so it works
 * identically on native and web.
 */

type Json = unknown;

const toSnake = (key: string): string =>
  key.replace(/[A-Z]/g, (m) => `_${m.toLowerCase()}`);

const toCamel = (key: string): string =>
  key.replace(/_([a-z0-9])/g, (_, c: string) => c.toUpperCase());

function convertKeys(value: Json, mapKey: (k: string) => string): Json {
  if (Array.isArray(value)) {
    return value.map((v) => convertKeys(v, mapKey));
  }
  if (value !== null && typeof value === "object") {
    const out: Record<string, Json> = {};
    for (const [k, v] of Object.entries(value as Record<string, Json>)) {
      out[mapKey(k)] = convertKeys(v, mapKey);
    }
    return out;
  }
  return value;
}

export const snakeizeKeys = (value: Json): Json => convertKeys(value, toSnake);
export const camelizeKeys = (value: Json): Json => convertKeys(value, toCamel);
