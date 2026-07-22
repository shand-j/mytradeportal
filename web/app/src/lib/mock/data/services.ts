import type { ServiceOffering } from '@/types';

export const mockServices: ServiceOffering[] = [
  { id: 'svc-001', name: 'Emergency Electrical', description: '24/7 emergency callout for power cuts, faults, and dangerous situations', basePrice: 150, estimatedDuration: 120, category: 'Emergency', isActive: true },
  { id: 'svc-002', name: 'EICR Inspection', description: 'Electrical Installation Condition Report and certification', basePrice: 180, estimatedDuration: 120, category: 'Testing', isActive: true },
  { id: 'svc-003', name: 'Full Rewire', description: 'Complete property rewire including new consumer unit and certification', basePrice: 4500, estimatedDuration: 2400, category: 'Installation', isActive: true },
  { id: 'svc-004', name: 'Consumer Unit Upgrade', description: 'Replace old fuse board with modern RCBO consumer unit', basePrice: 650, estimatedDuration: 240, category: 'Installation', isActive: true },
  { id: 'svc-005', name: 'EV Charger Installation', description: 'Supply and install 7kW EV charger with DNO notification', basePrice: 1800, estimatedDuration: 480, category: 'Installation', isActive: true },
  { id: 'svc-006', name: 'Solar PV Installation', description: 'Install solar panels with inverter and MCS certification', basePrice: 5500, estimatedDuration: 1440, category: 'Renewable', isActive: true },
  { id: 'svc-007', name: 'Smart Home Setup', description: 'Install smart lighting, switches, and home automation', basePrice: 1500, estimatedDuration: 960, category: 'Smart', isActive: true },
  { id: 'svc-008', name: 'Lighting Upgrade', description: 'Replace old lighting with energy-efficient LED systems', basePrice: 350, estimatedDuration: 180, category: 'Installation', isActive: true },
];
