import type { Review } from '@/types';
import { mockCustomers } from './customers';

const getCustomer = (id: string) => mockCustomers.find(c => c.id === id)!;

export const mockReviews: Review[] = [
  {
    id: 'rev-001', customerId: 'cust-001', customer: getCustomer('cust-001'),
    platform: 'google', rating: 5,
    reviewText: 'Absolutely brilliant work on our bathroom! Mike was professional, tidy, and kept us informed throughout. The finished result exceeded our expectations. Would highly recommend to anyone looking for a reliable plumber in South London.',
    reviewerName: 'Sarah Johnson', responded: true,
    responseText: 'Thank you so much Sarah! It was a pleasure working on your bathroom. Enjoy your new space!',
    respondedAt: '2025-06-15T12:00:00Z', reviewDate: '2025-06-15',
  },
  {
    id: 'rev-002', customerId: 'cust-004', customer: getCustomer('cust-004'),
    platform: 'google', rating: 4,
    reviewText: 'Great boiler installation work. Slight delay on the first day but Mike communicated well and the final result is excellent. Boiler working perfectly.',
    reviewerName: 'James Brown', responded: true,
    responseText: 'Thanks James! Apologies for the slight delay on day one — supply chain issues. Glad the boiler is keeping you warm!',
    respondedAt: '2025-06-13T10:00:00Z', reviewDate: '2025-06-12',
  },
  {
    id: 'rev-003', customerId: 'cust-005', customer: getCustomer('cust-005'),
    platform: 'google', rating: 2,
    reviewText: 'Took longer than originally quoted and there was some mess left behind after the gutter work. The repair itself seems fine but communication could have been better about the timeline.',
    reviewerName: 'Lisa Taylor', responded: false,
    responseText: null, respondedAt: null, reviewDate: '2025-06-08',
  },
  {
    id: 'rev-004', customerId: 'cust-006', customer: getCustomer('cust-006'),
    platform: 'google', rating: 5,
    reviewText: 'Best plumber in South London without a doubt! Mike has done multiple jobs for us over the years — always reliable, fairly priced, and top quality work. Cannot recommend highly enough.',
    reviewerName: 'Tom Harris', responded: true,
    responseText: 'Tom, you are too kind! Always a pleasure helping you out. Thanks for being such a loyal customer.',
    respondedAt: '2025-06-06T09:00:00Z', reviewDate: '2025-06-05',
  },
  {
    id: 'rev-005', customerId: 'cust-008', customer: getCustomer('cust-008'),
    platform: 'google', rating: 4,
    reviewText: 'Professional service for our rental properties. Good communication with tenants and clear invoicing. Would use again.',
    reviewerName: 'Mark Davis', responded: true,
    responseText: 'Thanks Mark! Happy to support your rental portfolio.',
    respondedAt: '2025-05-20T14:00:00Z', reviewDate: '2025-05-18',
  },
  {
    id: 'rev-006', customerId: 'cust-007', customer: getCustomer('cust-007'),
    platform: 'google', rating: 4,
    reviewText: 'Quick response to our low pressure issue. Mike diagnosed the problem fast and had it sorted same day. Fair pricing too.',
    reviewerName: 'Rachel Green', responded: true,
    responseText: 'Glad we could get your pressure back to normal Rachel!',
    respondedAt: '2025-06-14T11:00:00Z', reviewDate: '2025-06-13',
  },
  {
    id: 'rev-007', customerId: 'cust-001', customer: getCustomer('cust-001'),
    platform: 'google', rating: 5,
    reviewText: 'Second time using Mike\'s Plumbing and just as impressed as the first. Replaced our kitchen tap quickly and cleanly.',
    reviewerName: 'Sarah Johnson', responded: true,
    responseText: 'Thanks for coming back to us Sarah! Always here when you need us.',
    respondedAt: '2025-06-19T10:00:00Z', reviewDate: '2025-06-18',
  },
  {
    id: 'rev-008', customerId: 'cust-002', customer: getCustomer('cust-002'),
    platform: 'google', rating: 5,
    reviewText: 'Came out within an hour for our emergency leak. Fast, professional, and stopped the damage getting worse. Lifesavers!',
    reviewerName: 'David Smith', responded: false,
    responseText: null, respondedAt: null, reviewDate: '2025-06-19',
  },
];
