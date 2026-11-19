# E1 — Customer login (mobile, iOS)

Captured 2026-10-24 against production, same rig as `../a3-onboarding/`.

**Result: PASS.**

The customer account `john.shand06+qeprobe@gmail.com` (CRM contact "QE Probe" on
Shand 1 Electrical, created by the web wave's portal intake) was claimed via
`POST /customer/register` with a QE-set password (`QeCustomer123`) — the register
endpoint sets a password on the passwordless auto-provisioned account.

| # | Shot | What it shows |
|---|---|---|
| 01 | `01-customer-entry.png` | Entry → "I'm a Customer": code/slug entry + Customer login |
| 02 | `02-customer-login.png` | Customer login screen |
| 03 | `03-invalid-credentials.png` | Wrong password → "Invalid email or password." |
| 04 | `04-logged-in-home.png` | Successful login → customer home (white-label red theme): AI triage card, "1 quote generating", the web wave's accepted request card |

Note: the tenant's white-label theme (red) applies across the whole customer app —
visible in all customer shots here and in `../e2-quote-request/`.
