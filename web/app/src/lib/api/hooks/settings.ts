import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api/client';
import type { ApiError } from '@/lib/api/client';
import type { Tenant } from '@/types';

const settingsKeys = {
  all: ['settings'] as const,
};

type TenantKeyMap = Array<[keyof Tenant, string]>;

const directFieldMap: TenantKeyMap = [
  ['name', 'name'],
  ['email', 'email'],
  ['phone', 'phone'],
  ['website', 'website'],
  ['address', 'address'],
  ['logoUrl', 'logo_url'],
  ['primaryColor', 'primary_color'],
  ['secondaryColor', 'secondary_color'],
  ['planTier', 'plan_tier'],
  ['googlePlaceId', 'google_place_id'],
];

const pricingFieldMap: TenantKeyMap = [
  ['hourlyLaborRate', 'hourly_labour_rate'],
  ['dailyLaborRate', 'daily_labour_rate'],
  ['mateDailyRate', 'mate_daily_rate'],
  ['matePercent', 'mate_percent'],
  ['markupPercentage', 'markup_percentage'],
  ['minMarginPercent', 'min_margin_percent'],
  ['priceTolerancePercent', 'price_tolerance_percent'],
  ['minimumCharge', 'minimum_charge'],
  ['vatRate', 'vat_rate'],
];

export function mapTenantUpdatePayload(data: Partial<Tenant>): Record<string, unknown> {
  const payload: Record<string, unknown> = {};

  for (const [sourceKey, targetKey] of directFieldMap) {
    if (data[sourceKey] !== undefined) {
      payload[targetKey] = data[sourceKey];
    }
  }

  const settings: Record<string, unknown> = {};
  for (const [sourceKey, targetKey] of pricingFieldMap) {
    if (data[sourceKey] !== undefined) {
      settings[targetKey] = data[sourceKey];
    }
  }

  if (Object.keys(settings).length > 0) {
    payload.settings = settings;
  }

  return payload;
}

export function useSettings() {
  return useQuery<Tenant, ApiError>({
    queryKey: settingsKeys.all,
    queryFn: () => api.get('/tenants/me'),
  });
}

export function useUpdateSettings() {
  const queryClient = useQueryClient();

  return useMutation<Tenant, ApiError, Partial<Tenant>>({
    mutationFn: (data) => api.patch('/tenants/me', mapTenantUpdatePayload(data)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: settingsKeys.all });
    },
  });
}
