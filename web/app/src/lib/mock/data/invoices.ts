import type { Invoice } from '@/types';
import { mockCustomers } from './customers';

const getCustomer = (id: string) => mockCustomers.find(c => c.id === id)!;

export const mockInvoices: Invoice[] = [
  {
    id: 'inv-001', reference: 'INV-2025-0089', customerId: 'cust-001', customer: getCustomer('cust-001'),
    jobId: 'job-009', quoteId: null, status: 'paid',
    lineItems: [
      { id: 'ili-001', description: 'Consumer unit upgrade (18-way RCBO)', quantity: 1, unit: 'unit', unitPrice: 480, total: 480 },
      { id: 'ili-002', description: 'Labour (3 hours)', quantity: 3, unit: 'hours', unitPrice: 75, total: 225 },
      { id: 'ili-003', description: 'Electrical certification', quantity: 1, unit: 'cert', unitPrice: 85, total: 85 },
      { id: 'ili-004', description: 'Materials (cable, conduit, accessories)', quantity: 1, unit: 'kit', unitPrice: 60, total: 60 },
    ],
    subtotal: 850, vatAmount: 170, vatRate: 20, total: 1020,
    amountPaid: 1020, amountDue: 0,
    issueDate: '2025-06-18', dueDate: '2025-07-02', paidAt: '2025-06-18T16:00:00Z',
    paymentMethod: 'card', createdAt: '2025-06-18T10:30:00Z',
  },
  {
    id: 'inv-002', reference: 'INV-2025-0088', customerId: 'cust-004', customer: getCustomer('cust-004'),
    jobId: 'job-010', quoteId: null, status: 'viewed',
    lineItems: [
      { id: 'ili-005', description: 'LED fire-rated downlights (18)', quantity: 18, unit: 'units', unitPrice: 28, total: 504 },
      { id: 'ili-006', description: 'Labour (3 hours)', quantity: 3, unit: 'hours', unitPrice: 75, total: 225 },
      { id: 'ili-007', description: 'Disposal of old fittings', quantity: 1, unit: 'job', unitPrice: 45, total: 45 },
    ],
    subtotal: 774, vatAmount: 154.80, vatRate: 20, total: 928.80,
    amountPaid: 0, amountDue: 928.80,
    issueDate: '2025-06-17', dueDate: '2025-07-01', paidAt: null,
    paymentMethod: null, createdAt: '2025-06-17T15:00:00Z',
  },
  {
    id: 'inv-003', reference: 'INV-2025-0087', customerId: 'cust-002', customer: getCustomer('cust-002'),
    jobId: null, quoteId: 'quote-002', status: 'sent',
    lineItems: [
      { id: 'ili-008', description: 'Emergency callout', quantity: 1, unit: 'call', unitPrice: 150, total: 150 },
      { id: 'ili-009', description: 'RCD fault diagnosis & repair', quantity: 1, unit: 'job', unitPrice: 180, total: 180 },
      { id: 'ili-010', description: 'Replacement RCBO', quantity: 1, unit: 'unit', unitPrice: 65, total: 65 },
      { id: 'ili-011', description: 'Labour (1.5 hours)', quantity: 1.5, unit: 'hours', unitPrice: 75, total: 112.50 },
    ],
    subtotal: 507.50, vatAmount: 101.50, vatRate: 20, total: 609,
    amountPaid: 0, amountDue: 609,
    issueDate: '2025-06-20', dueDate: '2025-07-04', paidAt: null,
    paymentMethod: null, createdAt: '2025-06-20T09:30:00Z',
  },
  {
    id: 'inv-004', reference: 'INV-2025-0086', customerId: 'cust-005', customer: getCustomer('cust-005'),
    jobId: null, quoteId: null, status: 'overdue',
    lineItems: [
      { id: 'ili-012', description: 'Extractor fan installation (bathroom)', quantity: 1, unit: 'unit', unitPrice: 120, total: 120 },
      { id: 'ili-013', description: 'Timer overrun & isolator', quantity: 1, unit: 'kit', unitPrice: 65, total: 65 },
      { id: 'ili-014', description: 'Labour (2 hours)', quantity: 2, unit: 'hours', unitPrice: 75, total: 150 },
    ],
    subtotal: 335, vatAmount: 67, vatRate: 20, total: 402,
    amountPaid: 0, amountDue: 402,
    issueDate: '2025-06-03', dueDate: '2025-06-17', paidAt: null,
    paymentMethod: null, createdAt: '2025-06-03T16:00:00Z',
  },
  {
    id: 'inv-005', reference: 'INV-2025-0085', customerId: 'cust-007', customer: getCustomer('cust-007'),
    jobId: null, quoteId: 'quote-007', status: 'paid',
    lineItems: [
      { id: 'ili-015', description: 'EICR inspection & certificate', quantity: 1, unit: 'cert', unitPrice: 180, total: 180 },
      { id: 'ili-016', description: 'Socket replacement (6x)', quantity: 6, unit: 'units', unitPrice: 35, total: 210 },
      { id: 'ili-017', description: 'Cooker circuit upgrade', quantity: 1, unit: 'job', unitPrice: 320, total: 320 },
      { id: 'ili-018', description: 'Labour (1 day)', quantity: 1, unit: 'day', unitPrice: 350, total: 350 },
    ],
    subtotal: 1060, vatAmount: 212, vatRate: 20, total: 1272,
    amountPaid: 1272, amountDue: 0,
    issueDate: '2025-06-13', dueDate: '2025-06-27', paidAt: '2025-06-13T18:00:00Z',
    paymentMethod: 'card', createdAt: '2025-06-13T10:00:00Z',
  },
  {
    id: 'inv-006', reference: 'INV-2025-0084', customerId: 'cust-006', customer: getCustomer('cust-006'),
    jobId: 'job-005', quoteId: null, status: 'sent',
    lineItems: [
      { id: 'ili-019', description: 'EICR inspection', quantity: 1, unit: 'cert', unitPrice: 180, total: 180 },
      { id: 'ili-020', description: 'Minor remedial works', quantity: 1, unit: 'job', unitPrice: 85, total: 85 },
    ],
    subtotal: 265, vatAmount: 53, vatRate: 20, total: 318,
    amountPaid: 0, amountDue: 318,
    issueDate: '2025-06-20', dueDate: '2025-07-04', paidAt: null,
    paymentMethod: null, createdAt: '2025-06-20T14:00:00Z',
  },
];
