import { describe, it, expect } from 'vitest';

import { toAppointment } from './appointments';

describe('toAppointment', () => {
  it('maps the camelized API shape (startAt/endAt/address, no customer)', () => {
    // GET /appointments returns no embedded customer; startTime must come from
    // startAt or the calendar renders nothing.
    const appt = toAppointment({
      id: 'a1',
      tenantId: 't1',
      contactId: 'c1',
      jobId: null,
      title: 'Consumer unit replacement',
      startAt: '2026-09-09T09:00:00',
      endAt: '2026-09-09T13:00:00',
      status: 'confirmed',
      address: '22 Chestnut Avenue, Croydon',
      notes: null,
      createdAt: '2026-09-01T07:56:47',
      updatedAt: '2026-09-01T07:56:47',
    });

    expect(appt.customerId).toBe('c1');
    expect(appt.customer).toBeUndefined();
    expect(appt.startTime).toBe('2026-09-09T09:00:00');
    expect(appt.endTime).toBe('2026-09-09T13:00:00');
    expect(appt.propertyAddress).toBe('22 Chestnut Avenue, Croydon');
    expect(appt.status).toBe('confirmed');
    expect(new Date(appt.startTime).getHours()).toBe(9);
  });

  it('maps an embedded customer when present', () => {
    const appt = toAppointment({
      id: 'a1',
      contactId: 'c1',
      title: 'EICR',
      startAt: '2026-09-09T09:00:00',
      endAt: '2026-09-09T13:00:00',
      status: 'scheduled',
      customer: { id: 'c1', name: 'Emma Whitfield', phone: '07911 567890', createdAt: '2026-09-01T00:00:00' },
    });

    expect(appt.customer?.firstName).toBe('Emma');
    expect(appt.customer?.lastName).toBe('Whitfield');
  });
});
