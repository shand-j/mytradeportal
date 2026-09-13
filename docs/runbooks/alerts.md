# Alert Runbooks

One runbook per alert, five lines each: what it means / check first / likely
causes / action / escalation. Alerts arrive via Slack webhook + email
(Observability PRD §4.3). Dashboards are T+1 by design — only these alerts
interrupt the day.

## Budget 80% alert (monthly AI budget)

- **Means:** estimated month-to-date AI spend has crossed 80% of the £600 monthly budget.
- **Check first:** per-org cost leaderboard in Metabase — one org or broad?
- **Likely causes:** power-user concentration; retry storm; new feature (chat, intake briefs) driving unpriced volume.
- **Action:** identify the top driver; if a single org, apply cheaper-model routing and note for the monthly review; if broad, re-forecast and flag on Friday one-pager.
- **Escalate:** if projection exceeds 100% of budget before mid-month — founder + lead dev same day; consider tightening burst rate limits.

## Daily-spend-anomaly alert (>3× trailing-7-day mean)

- **Means:** yesterday's AI spend was over 3× the trailing 7-day average — spike, not trend.
- **Check first:** Langfuse traces for the spike window — retries, loop behaviour, token blow-ups.
- **Likely causes:** retry loop on a failing generation; abuse/scraping via intake forms; a runaway scheduled job; a bug multiplying calls per request.
- **Action:** if retry/loop, ship the fix or kill the job; if abuse, apply per-org burst rate limit and block source; log cause in the incident note.
- **Escalate:** if not explained within 4 hours or a second anomaly fires this week — lead dev investigates immediately; P0 if spend is still climbing.

## Fair-use-threshold alert (org crosses threshold)

- **Means:** an org has crossed the fair-use threshold (~3–5× beta p95 AI actions/mo).
- **Check first:** the org's usage pattern — legitimate heavy tradie or scripted/abnormal traffic?
- **Likely causes:** genuine power user; automated misuse; a customer-side flow (intake/chat) generating volume the org didn't ask for.
- **Action:** invisible guardrails only — cheaper-model routing + burst limits. Never block automatically; if restriction is warranted, human review and contact the tradie first (fair-use policy commitment).
- **Escalate:** founder decision before any customer-visible action; recurring crossings by the same org feed the monthly pricing review.

## Rollup-job-failure alert (nightly rollups)

- **Means:** last night's rollup job failed — dashboards are silently stale, not just empty of insight.
- **Check first:** job logs for the failing step (event table read, aggregation, write); confirm whether `ai_call_events` is still growing.
- **Likely causes:** schema drift after a migration; Postgres timeout on event volume; a bad deploy touching the event schema.
- **Action:** re-run the rollup manually after fixing; verify dashboards show yesterday's data; events are fail-open so no data was lost — only the aggregation.
- **Escalate:** if dashboards are stale >48h or the failure recurs after a fix — lead dev; flag on the Friday one-pager, as pricing decisions depend on this data.
