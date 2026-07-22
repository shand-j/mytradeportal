import type { Appointment } from '@/types';
import { mockCustomers } from './customers';

const getCustomer = (id: string) => mockCustomers.find(c => c.id === id)!;

export const mockAppointments: Appointment[] = [
  {
    id: 'appt-001', customerId: 'cust-004', customer: getCustomer('cust-004'),
    jobId: 'job-002', title: 'Smart Home Installation',
    startTime: '2025-06-23T09:00:00', endTime: '2025-06-23T17:00:00',
    serviceType: 'Smart Home Installation', propertyAddress: '5 Chestnut Drive, London NW3 2ST',
    status: 'in_progress', technicianName: 'Tom Watts',
  },
  {
    id: 'appt-002', customerId: 'cust-002', customer: getCustomer('cust-002'),
    jobId: 'job-003', title: 'Emergency — RCD Fault',
    startTime: '2025-06-23T14:00:00', endTime: '2025-06-23T16:00:00',
    serviceType: 'Emergency Electrical', propertyAddress: '18 Maple Avenue, London SW11 3BD',
    status: 'scheduled', technicianName: 'Raj Patel',
  },
  {
    id: 'appt-003', customerId: 'cust-007', customer: getCustomer('cust-007'),
    jobId: 'job-004', title: 'EICR & Remedial Works',
    startTime: '2025-06-24T08:00:00', endTime: '2025-06-24T14:00:00',
    serviceType: 'EICR & Remedial', propertyAddress: '64 Willow Way, London SE22 9MN',
    status: 'scheduled', technicianName: 'Raj Patel',
  },
  {
    id: 'appt-004', customerId: 'cust-008', customer: getCustomer('cust-008'),
    jobId: 'job-006', title: 'Solar PV Installation',
    startTime: '2025-06-24T08:00:00', endTime: '2025-06-24T17:00:00',
    serviceType: 'Solar PV Installation', propertyAddress: '37 Ash Grove, London SW4 7JK',
    status: 'scheduled', technicianName: 'Tom Watts',
  },
  {
    id: 'appt-005', customerId: 'cust-003', customer: getCustomer('cust-003'),
    jobId: 'job-007', title: 'EV Charger Site Survey',
    startTime: '2025-06-25T10:00:00', endTime: '2025-06-25T11:00:00',
    serviceType: 'EV Charger Survey', propertyAddress: '73 Birch Lane, London E14 5PQ',
    status: 'scheduled', technicianName: 'Tom Watts',
  },
  {
    id: 'appt-006', customerId: 'cust-001', customer: getCustomer('cust-001'),
    jobId: 'job-001', title: 'Full Property Rewire',
    startTime: '2025-06-28T08:00:00', endTime: '2025-06-28T17:00:00',
    serviceType: 'Full Rewire', propertyAddress: '42 Oak Street, London SE1 4RT',
    status: 'scheduled', technicianName: 'Tom Watts',
  },
  {
    id: 'appt-007', customerId: 'cust-006', customer: getCustomer('cust-006'),
    jobId: null, title: 'EICR — Rental Property',
    startTime: '2025-06-26T10:00:00', endTime: '2025-06-26T12:00:00',
    serviceType: 'EICR', propertyAddress: '91 Elm Street, London N1 6GH',
    status: 'scheduled', technicianName: 'Amy Chen',
  },
  {
    id: 'appt-008', customerId: 'cust-004', customer: getCustomer('cust-004'),
    jobId: null, title: 'Outdoor Lighting Install',
    startTime: '2025-06-27T14:00:00', endTime: '2025-06-27T17:00:00',
    serviceType: 'Outdoor Lighting', propertyAddress: '5 Chestnut Drive, London NW3 2ST',
    status: 'scheduled', technicianName: 'Amy Chen',
  },
];
