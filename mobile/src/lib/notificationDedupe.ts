/**
 * Session-scoped dedupe between remote Expo pushes and the local fallback
 * alert (`useQuoteReadyWatcher`).
 *
 * One backend event (e.g. quote_ready) reaches the device twice: as a remote
 * push carrying `{ type, id, link }`, and again as the polled notifications
 * row (`type` + `link`). Both channels resolve to the same entity, so a
 * `type:entityId` key correlates them. When the push side was received or
 * tapped, the local fallback for that entity is suppressed; otherwise the
 * fallback fires at most once per entity per app session.
 *
 * Module-level state survives watcher unmounts/remounts and resets only with
 * the JS runtime (app relaunch).
 */

const pushDeliveredKeys = new Set<string>();
const localAlertFiredKeys = new Set<string>();

/** Trailing UUID of a notification link, e.g. "/quotes/{uuid}". */
function entityIdFromLink(link: string | null): string | null {
  const match = link?.match(/\/([0-9a-f]{8}-[0-9a-f-]{27,})(?:\/)?$/i);
  return match ? match[1] : null;
}

/**
 * Correlation key for one notification entity. The entity id comes from the
 * push payload's `id`, falling back to the trailing UUID of `link`; the link
 * itself is the last resort so link-only rows still dedupe against each
 * other. Returns null when nothing identifiable is available.
 */
export function dedupeKey(
  type: string | null,
  link: string | null,
  id: string | null = null
): string | null {
  const entity = id ?? entityIdFromLink(link);
  if (type && entity) return `${type}:${entity}`;
  if (link) return `link:${link}`;
  return null;
}

/** Record that a remote push for this entity was received or tapped. */
export function markRemotePushDelivered(key: string | null): void {
  if (key) pushDeliveredKeys.add(key);
}

/**
 * Whether the local fallback alert may fire for this entity: only when no
 * remote push for it was delivered this session and the fallback has not
 * fired for it yet. A granted call consumes the one allowed fire.
 */
export function shouldFireLocalAlert(key: string | null): boolean {
  if (!key) return true;
  if (pushDeliveredKeys.has(key) || localAlertFiredKeys.has(key)) return false;
  localAlertFiredKeys.add(key);
  return true;
}
