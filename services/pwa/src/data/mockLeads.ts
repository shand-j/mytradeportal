import { Lead } from "../types";

export const MOCK_LEADS: Lead[] = [
  {
    id: "1",
    title: "Consumer unit upgrade",
    postcode: "SK8 3NJ",
    urgency: "today",
    source: "app",
    customerName: "Jane Homeowner",
    customerEmail: "jane@example.com",
    customerPhone: "07700 123 456",
    estimate: "£545-£620",
    badge: "New",
    status: "new",
    note: "3-bed house. Board is in the garage. Customer has a dog.",
    mediaIds: ["m1"],
    createdAt: new Date(Date.now() - 2 * 86400000).toISOString(),
  },
  {
    id: "2",
    title: "EV charger install",
    postcode: "M20 1AA",
    urgency: "today",
    source: "whatsapp",
    customerName: "John Driver",
    customerEmail: "john@example.com",
    customerPhone: "07700 654 321",
    estimate: "Site visit",
    badge: "Flagged",
    status: "new",
    note: "Messaged via WhatsApp. Wants 7kW charger on driveway.",
    mediaIds: ["m2"],
    createdAt: new Date(Date.now() - 86400000).toISOString(),
    preferredChannel: "whatsapp",
  },
  {
    id: "3",
    title: "Additional sockets",
    postcode: "M1 2AB",
    urgency: "this_week",
    source: "qr",
    customerName: "Alice Builder",
    customerEmail: "alice@example.com",
    customerPhone: "07700 111 222",
    estimate: "£300-£400",
    badge: "Draft",
    status: "draft",
    note: "Scanned QR code at site office.",
    createdAt: new Date(Date.now() - 3 * 86400000).toISOString(),
  },
];

export function getLeadSourceLabel(source: Lead["source"]): string {
  const labels: Record<Lead["source"], string> = {
    app: "Customer app",
    qr: "QR code",
    web: "Web form",
    whatsapp: "WhatsApp",
    sms: "SMS",
    phone: "Phone",
    manual: "Manual",
  };
  return labels[source] ?? source;
}
