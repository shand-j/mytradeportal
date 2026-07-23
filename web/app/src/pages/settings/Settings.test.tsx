import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';

import { renderWithProviders } from '@/test/test-utils';
import { Settings } from './Settings';

const mockUseSettings = vi.fn();
const mockMutate = vi.fn();
const mockUseUpdateSettings = vi.fn();
const mockUseFeatureFlags = vi.fn(() => ({ data: {}, isLoading: false, error: null }));

vi.mock('@/lib/api/hooks', () => ({
  useSettings: () => mockUseSettings(),
  useUpdateSettings: () => mockUseUpdateSettings(),
  useFeatureFlags: () => mockUseFeatureFlags(),
}));

const mockTenant = {
  id: 'tenant-1',
  name: 'Mikes Plumbing Ltd',
  slug: 'mikes-plumbing',
  logoUrl: null,
  primaryColor: '#D4650A',
  secondaryColor: '#1C1917',
  hourlyLaborRate: 65,
  dailyLaborRate: 420,
  mateDailyRate: 240,
  matePercent: 55,
  markupPercentage: 20,
  minMarginPercent: 15,
  priceTolerancePercent: 10,
  minimumCharge: 120,
  vatRate: 20,
  email: 'hello@mikesplumbing.co.uk',
  phone: '020 7946 0123',
  website: 'https://mikesplumbing.co.uk',
  address: '123 High Street, London',
  planTier: 'professional',
  googlePlaceId: null,
  createdAt: '2025-01-01T00:00:00Z',
};

describe('Settings', () => {
  beforeEach(() => {
    mockMutate.mockReset();
    mockUseUpdateSettings.mockReturnValue({ mutate: mockMutate, isPending: false });
    // Feature flags default off, matching production defaults.
    mockUseFeatureFlags.mockReturnValue({ data: {}, isLoading: false, error: null });
  });

  it('renders a loading skeleton', () => {
    mockUseSettings.mockReturnValue({ data: undefined, isLoading: true, error: null });
    renderWithProviders(<Settings />);
    expect(document.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('renders an error message', () => {
    mockUseSettings.mockReturnValue({ data: mockTenant, isLoading: false, error: new Error('boom') });
    renderWithProviders(<Settings />);
    expect(screen.getByText(/failed to load settings/i)).toBeInTheDocument();
  });

  it('renders business settings and can save', async () => {
    mockUseSettings.mockReturnValue({ data: mockTenant, isLoading: false, error: null });
    renderWithProviders(<Settings />);

    expect(screen.getByRole('heading', { name: 'Settings' })).toBeInTheDocument();
    expect(screen.getByDisplayValue('Mikes Plumbing Ltd')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /save business/i }));

    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Mikes Plumbing Ltd',
          email: 'hello@mikesplumbing.co.uk',
          hourlyLaborRate: 65,
          dailyLaborRate: 420,
          mateDailyRate: 240,
          matePercent: 55,
          markupPercentage: 20,
          minMarginPercent: 15,
          priceTolerancePercent: 10,
          minimumCharge: 120,
          vatRate: 20,
        }),
        expect.any(Object),
      );
    });
  });

  it('blocks business save when pricing values are out of bounds', async () => {
    mockUseSettings.mockReturnValue({ data: mockTenant, isLoading: false, error: null });
    renderWithProviders(<Settings />);

    const markupInput = screen.getByLabelText('Markup (%)');
    fireEvent.change(markupInput, { target: { value: '999' } });

    expect(screen.getByText(/fix pricing fields before saving/i)).toBeInTheDocument();
    expect(screen.getByText(/markup must be between 0 and 100/i)).toBeInTheDocument();

    const saveButton = screen.getByRole('button', { name: /save business/i });
    expect(saveButton).toBeDisabled();

    fireEvent.click(saveButton);
    await waitFor(() => {
      expect(mockMutate).not.toHaveBeenCalled();
    });
  });

  it('switches to the branding tab', () => {
    mockUseSettings.mockReturnValue({ data: mockTenant, isLoading: false, error: null });
    renderWithProviders(<Settings />);

    fireEvent.click(screen.getByRole('button', { name: /branding/i }));
    expect(screen.getByText(/click to upload logo/i)).toBeInTheDocument();
    expect(screen.getByDisplayValue('#D4650A')).toBeInTheDocument();
  });

  it('hides the integrations tab when the feature flag is off', () => {
    mockUseSettings.mockReturnValue({ data: mockTenant, isLoading: false, error: null });
    renderWithProviders(<Settings />);

    expect(screen.queryByRole('button', { name: /integrations/i })).not.toBeInTheDocument();
  });

  it('toggles an integration connection', () => {
    mockUseFeatureFlags.mockReturnValue({
      data: { externalIntegrations: true, voiceAiInsights: false, demandForecasting: false },
      isLoading: false,
      error: null,
    });
    mockUseSettings.mockReturnValue({ data: mockTenant, isLoading: false, error: null });
    renderWithProviders(<Settings />);

    fireEvent.click(screen.getByRole('button', { name: /integrations/i }));
    const disconnectBtn = screen.getAllByRole('button', { name: /disconnect/i })[0];
    fireEvent.click(disconnectBtn);

    fireEvent.click(screen.getByRole('button', { name: /save integrations/i }));
    expect(mockMutate).toHaveBeenCalled();
  });
});
