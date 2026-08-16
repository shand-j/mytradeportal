import { Quote } from "../types";

export const MOCK_QUOTES: Quote[] = [
  {
    id: "q1",
    leadId: "1",
    customerName: "Jane Homeowner",
    title: "Consumer unit upgrade",
    postcode: "SK8 3NJ",
    status: "sent",
    lineItems: [
      { id: "l1", kind: "labour", description: "Consumer unit replacement - 6-8 circuits", qty: "1", unit: "job", unitPrice: "520.00" },
      { id: "l2", kind: "materials", description: "Metal 12-way RCBO board + extras", qty: "1", unit: "job", unitPrice: "180.00" },
      { id: "l3", kind: "callout", description: "Call-out fee", qty: "1", unit: "item", unitPrice: "45.00" },
    ],
    assumptions: ["Stud/plasterboard walls", "Consumer unit is accessible", "No asbestos present"],
    aiConfidence: 78,
    sentAt: new Date(Date.now() - 86400000).toISOString(),
    expiresAt: new Date(Date.now() + 6 * 86400000).toISOString(),
    vatRate: 0.2,
  },
  {
    id: "q2",
    leadId: "2",
    customerName: "John Driver",
    title: "EV charger install",
    postcode: "M20 1AA",
    status: "draft",
    lineItems: [
      { id: "l4", kind: "labour", description: "EV charge point installation", qty: "1", unit: "job", unitPrice: "450.00" },
      { id: "l5", kind: "materials", description: "7kW charge point & cable", qty: "1", unit: "job", unitPrice: "320.00" },
    ],
    assumptions: ["Driveway access available", "Consumer unit has spare way"],
    aiConfidence: 65,
    vatRate: 0.2,
  },
];

export function getQuoteTotal(quote: Quote): { subtotal: number; vat: number; total: number } {
  const subtotal = quote.lineItems.reduce((sum, item) => {
    const qty = parseFloat(item.qty) || 0;
    const price = parseFloat(item.unitPrice) || 0;
    return sum + qty * price;
  }, 0);
  const vat = subtotal * quote.vatRate;
  return { subtotal, vat, total: subtotal + vat };
}
