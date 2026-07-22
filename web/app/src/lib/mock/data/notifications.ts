import type { Notification } from '@/types';

export const mockNotifications: Notification[] = [
  { id: 'notif-001', type: 'success', title: 'Quote accepted', message: 'Sarah Johnson accepted quote Q-2025-0042 for £4,410', entityType: 'quote', entityId: 'quote-001', read: false, createdAt: '2025-06-15T10:23:00Z' },
  { id: 'notif-002', type: 'warning', title: 'Quote expires soon', message: 'Quote Q-2025-0039 expires in 2 days', entityType: 'quote', entityId: 'quote-004', read: false, createdAt: '2025-06-17T09:00:00Z' },
  { id: 'notif-003', type: 'error', title: 'Invoice overdue', message: 'Invoice INV-2025-0086 is 3 days overdue — £450', entityType: 'invoice', entityId: 'inv-004', read: false, createdAt: '2025-06-20T00:00:00Z' },
  { id: 'notif-004', type: 'info', title: 'New review', message: 'David Smith left a 5-star review', entityType: 'review', entityId: 'rev-008', read: true, createdAt: '2025-06-19T08:00:00Z' },
  { id: 'notif-005', type: 'info', title: 'New quote request', message: 'Emma Wilson requested a quote via voice AI', entityType: 'quote', entityId: 'quote-003', read: true, createdAt: '2025-06-19T11:20:00Z' },
  { id: 'notif-006', type: 'success', title: 'Payment received', message: '£222 received for INV-2025-0089', entityType: 'invoice', entityId: 'inv-001', read: true, createdAt: '2025-06-18T16:00:00Z' },
  { id: 'notif-007', type: 'warning', title: 'Review needs response', message: 'Lisa Taylor left a 2-star review — needs reply', entityType: 'review', entityId: 'rev-003', read: false, createdAt: '2025-06-08T14:00:00Z' },
  { id: 'notif-008', type: 'info', title: 'Job starting tomorrow', message: 'Boiler Replacement for James Brown — 9AM', entityType: 'job', entityId: 'job-002', read: true, createdAt: '2025-06-22T18:00:00Z' },
];
