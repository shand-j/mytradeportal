import { describe, it, expect } from 'vitest';

import { toInvoice } from './invoices';

const baseInvoice = {
  id: 'inv-1',
  invoiceNumber: 'INV-001',
  contactId: 'c1',
  status: 'draft',
  subtotal: '375.00',
  vatRate: '0.20',
  vatAmount: '75.00',
  total: '450.00',
  issueDate: '2026-09-01T08:00:00',
  dueDate: '2026-09-15T08:00:00',
  createdAt: '2026-09-01T08:00:00',
};

describe('toInvoice', () => {
  it('uses the API per-line total instead of re-multiplying it', () => {
    // Regression: total was computed as total × unitPrice, so a 1 × £180 line
    // rendered as £32,400.
    const invoice = toInvoice({
      ...baseInvoice,
      lineItems: [
        { id: 'l1', description: 'Consumer unit', quantity: '1.00', unitPrice: '180.0000', total: '180.0000' },
      ],
    });

    expect(invoice.lineItems).toHaveLength(1);
    expect(invoice.lineItems[0].total).toBe(180);
    expect(invoice.lineItems[0].unitPrice).toBe(180);
  });

  it('falls back to quantity × unit price when the line total is absent', () => {
    const invoice = toInvoice({
      ...baseInvoice,
      lineItems: [
        { id: 'l1', description: 'Labour', quantity: 5, unitPrice: 65 },
      ],
    });

    expect(invoice.lineItems[0].total).toBe(325);
  });

  it('accepts snake_case line items', () => {
    const invoice = toInvoice({
      ...baseInvoice,
      lineItems: undefined,
      line_items: [
        { id: 'l1', description: 'Sockets', quantity: '2.00', unit_price: '72.0000', total: '144.0000' },
      ],
    });

    expect(invoice.lineItems[0].total).toBe(144);
  });

  it('maps invoice-level totals and VAT rate', () => {
    const invoice = toInvoice({ ...baseInvoice, lineItems: [] });

    expect(invoice.subtotal).toBe(375);
    expect(invoice.vatRate).toBe(0.2);
    expect(invoice.vatAmount).toBe(75);
    expect(invoice.total).toBe(450);
    expect(invoice.amountDue).toBe(450);
  });
});
