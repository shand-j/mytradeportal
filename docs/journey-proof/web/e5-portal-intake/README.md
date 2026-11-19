# E5 — Portal intake: guest quote request + inline AI triage

- **Actor:** guest homeowner (no account)
- **Surface:** https://shand-1-electrical-lorg9.mytradeportal.co.uk/ (tenant portal host — wildcard DNS resolves correctly, 2026-10-23)
- **API:** `POST /businesses/shand-1-electrical-lorg9/quote-requests` (201), guest triage thread via `/public/threads/{qr_id}/messages` with the thread token from the intake ack
- **Captured:** 2026-10-23, production

## Steps

| # | Step | Expected | Observed | Result |
|---|------|----------|----------|--------|
| 1 | Open portal home | Tenant-branded landing with quote-request form | Shand 1 Electrical branding (red/purple), service chips (consumer unit, full rewire, EV charger, partial rewire), phone + address (`01-portal-home.png`) | PASS |
| 2 | Fill form (QE Probe / john.shand06+qeprobe@gmail.com / phone / consumer unit / 14 Example Terrace, LS1 4DY / tripping fuse box description) | Validation passes, submit enabled | Filled (`02-form-filled.png`) | PASS |
| 3 | Click REQUEST A QUOTE | Submitting state, then AI triage | "Sending your request…" (`03-submitting.png`) | PASS |
| 4 | Inline AI triage | Assistant asks a follow-up question | "A couple of quick questions — ASSISTANT: What is the current rating of your existing consumer unit?" with reply box + "No more questions — done" escape (`04-triage-progress.png`) | PASS |
| 5 | Reply to triage question | Answer accepted into thread | Answer sent via the guest thread (`05-triage-answer-sent.png`, `06-triage-progress.png`) | PASS |
| 6 | Finish | Confirmation with reference | "REQUEST RECEIVED — We're on it — you'll get an email when your quote is ready. Your reference: 19D7C00C" + explanation that the email link signs the customer into the portal (`99-final.png`) | PASS |

Note: the `account_created` email for this guest went to john.shand06+qeprobe@gmail.com (a real mailbox QE cannot read); template evidence for the equivalent email exists in `../i1-email-evidence/05-account-created.png` (captured via the mail.tm customer). The E8 guest chat thread is this same inline thread UI — the intake ack returns a `thread_token`, and the emailed triage link reopens this thread; captured here as steps 4–5.

**Overall: PASS**
