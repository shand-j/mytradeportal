import type { Tenant, User } from '@/types';

export const mockTenant: Tenant = {
  id: 'tenant-001',
  name: "Watts Electrical",
  slug: 'watts-electrical',
  logoUrl: '/logo-icon.jpg',
  primaryColor: '#D4650A',
  secondaryColor: '#2563EB',
  hourlyLaborRate: 75,
  markupPercentage: 30,
  minimumCharge: 150,
  vatRate: 20,
  email: 'tom@wattselectrical.co.uk',
  phone: '020 7946 0456',
  website: 'www.wattselectrical.co.uk',
  address: '42 Electric Avenue, London SE14 6QJ',
  planTier: 'professional',
  googlePlaceId: 'ChIJ9876543210',
  createdAt: '2024-01-15T00:00:00Z',
};

export const mockUsers: User[] = [
  {
    id: 'user-001',
    tenantId: 'tenant-001',
    fullName: 'Tom Watts',
    email: 'tom@wattselectrical.co.uk',
    phone: '07700 900111',
    role: 'admin',
    avatarUrl: '/avatar-mike.jpg',
    isActive: true,
  },
  {
    id: 'user-002',
    tenantId: 'tenant-001',
    fullName: 'Raj Patel',
    email: 'raj@wattselectrical.co.uk',
    phone: '07700 900222',
    role: 'technician',
    avatarUrl: null,
    isActive: true,
  },
  {
    id: 'user-003',
    tenantId: 'tenant-001',
    fullName: 'Amy Chen',
    email: 'amy@wattselectrical.co.uk',
    phone: '07700 900333',
    role: 'technician',
    avatarUrl: null,
    isActive: true,
  },
];
