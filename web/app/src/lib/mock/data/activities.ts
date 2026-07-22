import type { Activity } from '@/types';

export const mockActivities: Activity[] = [
  { id: 'act-001', type: 'quote_accepted', title: 'Quote Q-2025-0042 accepted by Sarah Johnson', description: 'Full Rewire — £10,404', entityType: 'quote', entityId: 'quote-001', createdAt: '2025-06-15T10:23:00Z' },
  { id: 'act-002', type: 'voice_call_handled', title: 'Voice AI handled quote enquiry call', description: 'Sarah Johnson — Full Rewire, 4m 32s call', entityType: 'quote', entityId: 'quote-001', createdAt: '2025-06-15T09:45:00Z' },
  { id: 'act-003', type: 'quote_sent', title: 'Quote Q-2025-0042 sent via email', description: 'Sent to sarah.johnson@email.com', entityType: 'quote', entityId: 'quote-001', createdAt: '2025-06-14T16:15:00Z' },
  { id: 'act-004', type: 'ai_quote_generated', title: 'AI generated quote Q-2025-0042', description: 'Full Rewire — £10,404 (94% confidence)', entityType: 'quote', entityId: 'quote-001', createdAt: '2025-06-14T15:42:00Z' },
  { id: 'act-005', type: 'invoice_paid', title: 'Invoice INV-2025-0089 paid', description: '£1,020 — Consumer unit upgrade', entityType: 'invoice', entityId: 'inv-001', createdAt: '2025-06-18T16:00:00Z' },
  { id: 'act-006', type: 'voice_call_handled', title: 'Voice AI booked emergency callout', description: 'David Smith — RCD fault, 3m 12s call', entityType: 'job', entityId: 'job-003', createdAt: '2025-06-18T08:15:00Z' },
  { id: 'act-007', type: 'job_scheduled', title: 'Job J-2025-0012 scheduled', description: 'Full Rewire — June 28', entityType: 'job', entityId: 'job-001', createdAt: '2025-06-15T10:30:00Z' },
  { id: 'act-008', type: 'customer_registered', title: 'New customer registered', description: 'Emma Wilson — emma.wilson@email.com', entityType: 'customer', entityId: 'cust-003', createdAt: '2025-06-19T11:20:00Z' },
  { id: 'act-009', type: 'voice_call_handled', title: 'Voice AI collected EV charger enquiry', description: 'Emma Wilson — Tesla Model 3, 5m 48s call', entityType: 'quote', entityId: 'quote-003', createdAt: '2025-06-19T10:30:00Z' },
  { id: 'act-010', type: 'ai_quote_generated', title: 'AI generated quote Q-2025-0040', description: 'EV Charger Installation — £2,304 (91% confidence)', entityType: 'quote', entityId: 'quote-003', createdAt: '2025-06-19T11:20:00Z' },
  { id: 'act-011', type: 'review_received', title: 'New 5-star review from David Smith', description: '"Voice AI was brilliant — booked my emergency call in under 5 minutes"', entityType: 'review', entityId: 'rev-008', createdAt: '2025-06-19T08:00:00Z' },
  { id: 'act-012', type: 'job_completed', title: 'Job J-2025-0005 completed', description: 'EICR — £318', entityType: 'job', entityId: 'job-005', createdAt: '2025-06-20T12:00:00Z' },
];
