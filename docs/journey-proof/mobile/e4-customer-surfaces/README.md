# E4 — Customer calendar / invoices / profile / notifications (mobile, iOS)

Captured 2026-10-24 as customer `john.shand06+qeprobe@gmail.com` on Shand 1
Electrical, against production.

**Result: PASS (all four surfaces render real data).**

**Seeded data (explicitly API-seeded for this run):** the brief expected the
earlier waves' data on the QE Probe contact, but the web wave's quote/invoice
data was created on a different (mail.tm) contact. So as trade user jshand89 the
following were created against the QE Probe contact (`97d95e92`): quote
`32d8b39e` (sent), job `95455e5d`, invoice `55939e51` (INV-007, issued + sent),
appointment `69a89206` (27 Oct 09:00–11:00).

| # | Shot | What it shows |
|---|---|---|
| 01 | `01-notifications.png` | Notifications: "No notifications yet" (empty state) |
| 02 | `02-invoices.png` | Invoices list (seeded invoice visible) |
| 03 | `03-invoice-detail.png` | Invoice detail: INV-007, £250, AWAITING PAYMENT, line items, issued/due dates; bank-transfer fallback copy (tenant has no Stripe — consistent with QE-W2/QE-W5) |
| 04 | `04-calendar-appointment.png` | Calendar/appointments: seeded "Consumer unit replacement — day 1", 27/10 09:00–11:00 |
| 05 | `05-profile.png` | Profile: contact details, "1 quote request", preferences |
| 06 | `06-logbox-webview-error-blocks-tabbar.png` | Defect evidence: the persistent `react-native-webview` error toast covers the tab bar; tapping a tab opens the full LogBox instead of navigating (dev-client manifestation of QE-M2-1) |

Note: notifications empty state is genuine — no customer notifications had fired
for this account (quote-ready emails go by email, not in-app).
