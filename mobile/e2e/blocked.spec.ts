import { test } from "@playwright/test";
import {
  api,
  apiRaw,
  createTestTenant,
  expect,
  loginCustomer,
  seedCustomer,
  seedLead,
  Tenant,
} from "./helpers";

// Blocked-customer enforcement (G31, N26): once a tenant blocks a customer
// (contact.is_blocked), the customer account must be a dead end — login,
// quote-request creation and chat are all refused server-side. These are
// API-level negative asserts (the CRM banner UI is covered by N26 in
// crm.spec.ts). Correct-credentials login must still fail so the 403 cannot
// be used to enumerate block status. One enforcement gap is encoded as
// test.fixme with the desired behaviour asserted (it fails today and flips
// to unexpected-pass when the backend is fixed): pre-block bearer tokens
// keep working on CurrentCustomerDep-only read surfaces.

const CUSTOMER_PASSWORD = "E2E-Customer-1";

test.describe.serial("S — Blocked-customer enforcement", () => {
  let tenant: Tenant;
  let customer: { email: string; fullName: string };
  let contactId: string;
  let customerId: string;
  let leadId: string;
  // Token minted BEFORE the block: a blocked customer keeps no valid session.
  let preBlockToken: string;

  test.beforeAll(async () => {
    tenant = await createTestTenant("blocked");
    customer = { email: "blocked-customer@e2e.example.com", fullName: "E2E Blocked Customer" };
    const lead = await seedLead(tenant, {
      title: "E2E Blocked lead",
      category: "consumer_unit",
      contact: {
        name: customer.fullName,
        email: customer.email,
        phone: "07700 900999",
        postcode: "SK8 3NJ",
      },
      urgency: "this_week",
    });
    const registration = await seedCustomer(tenant, {
      email: customer.email,
      password: CUSTOMER_PASSWORD,
      fullName: customer.fullName,
      phone: "07700 900999",
      quoteRequestId: lead.id,
    });
    contactId = registration.customer.contact_id as string;
    customerId = registration.customer.id as string;
    leadId = lead.id as string;

    const auth = await loginCustomer(tenant, {
      email: customer.email,
      password: CUSTOMER_PASSWORD,
    });
    preBlockToken = (auth.accessToken ?? auth.access_token) as string;

    await api(tenant, `/contacts/${contactId}/block`, {
      method: "POST",
      body: { reason: "E2E blocked for enforcement asserts" },
    });
  });

  test("G31: a blocked customer cannot log in, even with correct credentials", async () => {
    const res = await apiRaw(
      tenant,
      "/customer/login",
      {
        method: "POST",
        auth: false,
        body: { slug: tenant.slug, email: customer.email, password: CUSTOMER_PASSWORD },
      }
    );
    expect(res.status).toBe(403);
    expect(JSON.stringify(res.json)).toContain("customer_blocked");
  });

  test("G31: a blocked customer token is refused on chat (enforced surfaces)", async () => {
    // Chat: the /communications actor dependency enforces the block before
    // the thread is even looked up.
    const blocked = { ...tenant, token: preBlockToken };
    const chat = await apiRaw(blocked, "/communications", {
      method: "POST",
      body: { quote_request_id: leadId, channel: "in_app_chat", body: "hello?" },
    });
    expect(chat.status).toBe(403);
    expect(JSON.stringify(chat.json)).toContain("customer_blocked");
  });

  test.fixme(
    "G31: a blocked customer token is refused on read surfaces (quotes list)",
    async () => {
      // PRODUCT BUG (second surface): block enforcement lives per-endpoint —
      // /customer/login and the /communications actor check both refuse a
      // blocked customer, but get_current_customer (CurrentCustomerDep) never
      // checks contact.is_blocked, so a token minted BEFORE the block keeps
      // working on every read surface that only uses CurrentCustomerDep
      // (/customer/quotes here). The token must die with the block.
      const blocked = { ...tenant, token: preBlockToken };
      const quotes = await apiRaw(blocked, "/customer/quotes");
      expect(quotes.status).toBe(403);
      expect(JSON.stringify(quotes.json)).toContain("customer_blocked");
    }
  );

  test("G31: staff-side quote-request creation for a blocked customer is refused", async () => {
    const res = await apiRaw(tenant, "/quote-requests", {
      method: "POST",
      body: {
        contact_id: contactId,
        customer_id: customerId,
        source: "app",
        title: "E2E should not exist",
        category: "consumer_unit",
      },
    });
    expect(res.status).toBe(403);
    expect(JSON.stringify(res.json)).toContain("customer_blocked");
  });

  test(
    "G31: the public quote-request endpoint refuses a blocked logged-in customer",
    async () => {
      // submit_public_quote_request (routers/businesses.py) resolves the
      // logged-in customer's contact (or reuses one by case-insensitive
      // email) and enforces contact_is_blocked with the same 403 the
      // staff-side endpoint and login dependency return.
      const blocked = { ...tenant, token: preBlockToken };
      const res = await apiRaw(
        blocked,
        `/businesses/${tenant.slug}/quote-requests`,
        {
          method: "POST",
          auth: false,
          headers: { Authorization: `Bearer ${preBlockToken}` },
          body: {
            contact: {
              name: customer.fullName,
              email: customer.email,
              phone: "07700 900999",
              postcode: "SK8 3NJ",
            },
            category: "consumer_unit",
            title: "E2E blocked intake should fail",
            raw_text: null,
            structured_data: {},
            urgency: "this_week",
            preferred_dates: [],
            safety_review_required: false,
            marketing_consent: false,
          },
        }
      );
      expect(res.status).toBe(403);
    }
  );

  test("G31: unblocking restores access", async () => {
    await api(tenant, `/contacts/${contactId}/unblock`, { method: "POST" });
    const auth = await loginCustomer(tenant, {
      email: customer.email,
      password: CUSTOMER_PASSWORD,
    });
    expect(auth.accessToken ?? auth.access_token).toBeTruthy();
  });
});
