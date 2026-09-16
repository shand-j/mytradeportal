// Mailpit REST client for E2E email assertions.
//
// Staging and Railway PR environments route outbound email into a shared
// Mailpit instance instead of Resend (see docs/ci-pr-environments.md), so
// tests can assert that customer/tenant emails were actually sent and
// inspect their contents. The mailbox is shared across environments, so
// always filter by a recipient address that is unique to the test.
//
// Requires MAILPIT_URL (https://... up to the root, no trailing slash) and
// MAILPIT_BASIC_AUTH ("user:password") in the environment. When either is
// missing, `mailpitConfigured()` returns false and specs should skip.

const MAILPIT_URL = (process.env.MAILPIT_URL ?? "").replace(/\/$/, "");
const BASIC_AUTH = process.env.MAILPIT_BASIC_AUTH ?? "";

export function mailpitConfigured(): boolean {
  return Boolean(MAILPIT_URL && BASIC_AUTH);
}

interface MailpitMessageListItem {
  ID: string;
  To: Array<{ Address: string }>;
  Subject: string;
}

interface MailpitMessage {
  Subject: string;
  Text: string;
  HTML: string;
  From?: { Address?: string; Name?: string };
}

async function mailpitApi(path: string): Promise<unknown> {
  const res = await fetch(`${MAILPIT_URL}${path}`, {
    headers: { Authorization: `Basic ${btoa(BASIC_AUTH)}` },
  });
  if (!res.ok) {
    throw new Error(`Mailpit GET ${path} -> HTTP ${res.status}`);
  }
  return res.json();
}

export interface CapturedEmail {
  id: string;
  subject: string;
  text: string;
  html: string;
  /** Sender address from the From header (e.g. quotes@mytradeportal.co.uk). */
  from: string;
}

async function listMessages(
  to: string,
  subjectIncludes?: string,
): Promise<MailpitMessageListItem[]> {
  const list = (await mailpitApi("/api/v1/messages")) as { messages: MailpitMessageListItem[] };
  const wanted = to.toLowerCase();
  return list.messages.filter(
    (m) =>
      m.To.some((t) => (t.Address ?? "").toLowerCase() === wanted) &&
      (!subjectIncludes || m.Subject.includes(subjectIncludes)),
  );
}

/** Poll the mailbox until at least `minCount` emails to `to` (optionally
 * matching a subject substring) have arrived, then return them all —
 * newest first, in Mailpit list order. Throws on timeout. */
export async function waitForEmails(
  to: string,
  opts: { subjectIncludes?: string; minCount?: number; timeoutMs?: number } = {},
): Promise<CapturedEmail[]> {
  if (!mailpitConfigured()) {
    throw new Error("MAILPIT_URL / MAILPIT_BASIC_AUTH not set");
  }
  const timeoutMs = opts.timeoutMs ?? 60_000;
  const minCount = opts.minCount ?? 1;
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const matches = await listMessages(to, opts.subjectIncludes);
    if (matches.length >= minCount) {
      const full = await Promise.all(
        matches.map(async (m) => {
          const message = (await mailpitApi(`/api/v1/message/${m.ID}`)) as MailpitMessage;
          return {
            id: m.ID,
            subject: message.Subject,
            text: message.Text ?? "",
            html: message.HTML ?? "",
            from: message.From?.Address ?? "",
          };
        }),
      );
      return full;
    }
    if (Date.now() > deadline) {
      throw new Error(
        `only ${matches.length} Mailpit email(s) to ${to}` +
          (opts.subjectIncludes ? ` with subject containing "${opts.subjectIncludes}"` : "") +
          ` within ${timeoutMs}ms (wanted ${minCount})`,
      );
    }
    await new Promise((resolve) => setTimeout(resolve, 3_000));
  }
}

/** Poll the mailbox until an email to `to` (optionally matching a subject
 * substring) arrives, then return its full contents. Throws on timeout. */
export async function waitForEmail(
  to: string,
  opts: { subjectIncludes?: string; timeoutMs?: number } = {},
): Promise<CapturedEmail> {
  const [first] = await waitForEmails(to, { ...opts, minCount: 1 });
  return first;
}
