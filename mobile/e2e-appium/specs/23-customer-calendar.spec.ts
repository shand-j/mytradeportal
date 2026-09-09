/**
 * 23 — Customer calendar (Appointments): booked appointments from accepted
 * quotes are listed. Opportunistic — needs a confirmed appointment linked to
 * the E2E customer's contact (produced by the spec-20 accept flow or real
 * usage); skips with a log when the list is empty.
 */
import { loginAsCustomer } from "../helpers/auth";
import {
  closeDb,
  countRows,
  customerCredsConfigured,
  CUSTOMER_EMAIL,
  CUSTOMER_PASSWORD,
  dbConfigured,
} from "../helpers/api";
import { hasText, tapId, waitForText } from "../helpers/ui";

describe("23: customer calendar (appointments)", () => {
  if (!customerCredsConfigured()) {
    console.log("SKIP: E2E_CUSTOMER_EMAIL/E2E_CUSTOMER_PASSWORD not set");
    return;
  }

  before(async () => {
    await loginAsCustomer(CUSTOMER_EMAIL, CUSTOMER_PASSWORD);
  });

  after(async () => {
    await closeDb();
  });

  it("lists booked appointments from accepted quotes", async () => {
    await tapId("tab-calendar", 25000);
    await waitForText("Appointments", 15000);
    await waitForText("Upcoming appointments and bookings", 15000);

    if (await hasText("No upcoming bookings.")) {
      console.log("SKIP: no confirmed appointments for this customer");
      return;
    }

    // The first booking card shows its title; cross-check it against the DB
    // (appointments joined to the contact with the customer's email).
    if (dbConfigured()) {
      const rows = await countRows(
        "appointments a JOIN contacts c ON c.id = a.contact_id",
        "lower(c.email) = lower($1) AND a.status IN ('confirmed', 'completed')",
        [CUSTOMER_EMAIL]
      );
      expect(rows).toBeGreaterThanOrEqual(1);
    } else {
      console.log("SKIP: MTP_DB_URL not set — DB cross-check skipped");
    }
    // Card actions for the booking are present.
    const hasActions =
      (await hasText("Add to Calendar")) || (await hasText("Message"));
    expect(hasActions).toBe(true);
  });
});
