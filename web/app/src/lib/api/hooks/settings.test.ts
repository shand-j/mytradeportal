import { describe, expect, it } from 'vitest';

import { mapTenantUpdatePayload } from './settings';

describe('mapTenantUpdatePayload', () => {
  it('maps pricing fields to backend settings keys using UK labour spelling', () => {
    const payload = mapTenantUpdatePayload({
      hourlyLaborRate: 65,
      dailyLaborRate: 420,
      mateDailyRate: 250,
      matePercent: 55,
      markupPercentage: 20,
      minMarginPercent: 15,
      priceTolerancePercent: 10,
      minimumCharge: 120,
      vatRate: 20,
    });

    expect(payload).toEqual({
      settings: {
        hourly_labour_rate: 65,
        daily_labour_rate: 420,
        mate_daily_rate: 250,
        mate_percent: 55,
        markup_percentage: 20,
        min_margin_percent: 15,
        price_tolerance_percent: 10,
        minimum_charge: 120,
        vat_rate: 20,
      },
    });
  });

  it('maps direct tenant fields and omits undefined values', () => {
    const payload = mapTenantUpdatePayload({
      name: 'Updated Electrical Ltd',
      email: 'ops@example.com',
      website: null,
      planTier: 'professional',
      googlePlaceId: null,
    });

    expect(payload).toEqual({
      name: 'Updated Electrical Ltd',
      email: 'ops@example.com',
      website: null,
      plan_tier: 'professional',
      google_place_id: null,
    });
  });
});
