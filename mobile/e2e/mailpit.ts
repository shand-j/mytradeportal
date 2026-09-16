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
  subject: string;
  text: string;
  html: string;
}

/** Poll the mailbox until an email to `to` (optionally matching a subject
 * substring) arrives, then return its full contents. Throws on timeout. */
export async function waitForEmail(
  to: string,
  opts: { subjectIncludes?: string; timeoutMs?: number } = {},
): Promise<CapturedEmail> {
  if (!mailpitConfigured()) {
    throw new Error("MAILPIT_URL / MAILPIT_BASIC_AUTH not set");
  }
  const timeoutMs = opts.timeoutMs ?? 60_000;
  const deadline = Date.now() + timeoutMs;
  const wanted = to.toLowerCase();
  for (;;) {
    const list = (await mailpitApi("/api/v1/messages")) as { messages: MailpitMessageListItem[] };
    const match = list.messages.find(
      (m) =>
        m.To.some((t) => (t.Address ?? "").toLowerCase() === wanted) &&
        (!opts.subjectIncludes || m.Subject.includes(opts.subjectIncludes)),
    );
    if (match) {
      const full = (await mailpitApi(`/api/v1/message/${match.ID}`)) as MailpitMessage;
      return { subject: full.Subject, text: full.Text ?? "", html: full.HTML ?? "" };
    }
    if (Date.now() > deadline) {
      throw new Error(
        `no Mailpit email to ${to}` +
          (opts.subjectIncludes ? ` with subject containing "${opts.subjectIncludes}"` : "") +
          ` within ${timeoutMs}ms (mailbox holds ${list.messages.length} messages)`,
      );
    }
    await new Promise((resolve) => setTimeout(resolve, 3_000));
  }
}
