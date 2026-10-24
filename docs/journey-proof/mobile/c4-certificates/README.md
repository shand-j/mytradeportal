# C4 — Certificates (EICR) prototype (mobile, iOS)

Captured 2026-10-24 as trade user jshand89@gmail.com (Shand 1 Electrical) against
production, same rig as `../a3-onboarding/`.

**Result: PASS (prototype documented) — client-only, no backend.**

The certificates feature is a client-only prototype: data comes from
`mobile/src/lib/certificates` (local), there is no API persistence. Screenshots
document the current state.

| # | Shot | What it shows |
|---|---|---|
| 01 | `01-certificates-list.png` | `/(trade)/certificates`: "Digital EICR certificates", empty state |
| 02 | `02-certificate-new.png` | New EICR: customer/address header card, "No circuits recorded yet" |
| 03 | `03-circuit-form-empty.png` | Add-circuit form: designation, protective device, Zs measured/max, RCD trip, IR, live BS 7671 checks panel |
| 04 | `04-circuit-form-filled.png` | Form filled (kitchen ring final, 32A Type B MCB + 30mA RCD, Zs 0.55/1.44Ω, RCD 24ms) with live validation: Zs Pass, RCD Pass, overall **INCOMPLETE** while IR unparsable |
| 05 | `05-circuit-form-bs7671-pass.png` | IR corrected to 500 MΩ → all three rules Pass, overall **PASS** |
| 06 | `06-circuit-save-unresponsive.png` | The "Add circuit" (save) button did not respond to any synthetic tap (element click or coordinate tap), nor did Cancel — see QE-M2-6 |

## Findings

- **QE-M2-6 (S3, needs manual verification)** — On the EICR circuit form, the
  bottom action buttons ("Add circuit"/"Save circuit", "Cancel") accepted no taps
  under XCUITest automation while field inputs worked fine. An invisible keyboard
  window overlaying the lower ~300pt of the screen (y ≥ 566) is the likely cause in
  the simulator; the buttons sit inside that band and the form's layout does not
  move them above it. Needs a human device check to confirm whether real touches
  are affected. The live BS 7671 validation itself works (shots 04–05).
- Data is local-only by design (prototype) — no certificate appears on the API.
