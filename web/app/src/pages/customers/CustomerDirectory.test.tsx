import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { CustomerDirectory } from './CustomerDirectory';
import { useContacts, useCreateContact, useDeleteContact } from '@/lib/api/hooks';
import { renderPage, resetStores } from '@/test/test-utils';
import { mockCustomers } from '@/lib/mock/data/customers';

const defaultMutations = {
  mutate: vi.fn(),
  mutateAsync: vi.fn(),
  isPending: false,
  isIdle: true,
  isSuccess: false,
  isError: false,
  reset: vi.fn(),
  error: null,
  data: undefined,
  status: 'idle',
  failureCount: 0,
  failureReason: null,
  submittedAt: 0,
};

vi.mock('@/lib/api/hooks', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/lib/api/hooks')>();
  return {
    ...original,
    useContacts: vi.fn(() => ({ data: undefined, isLoading: true, error: null })),
    useCreateContact: vi.fn(() => defaultMutations),
    useDeleteContact: vi.fn(() => defaultMutations),
  };
});

describe('CustomerDirectory', () => {
  beforeEach(() => {
    resetStores();
    vi.stubEnv('VITE_GETADDRESS_IO_API_KEY', 'test-key');
    vi.mocked(useContacts).mockReturnValue({ data: mockCustomers, isLoading: false, error: null });
    vi.mocked(useCreateContact).mockReturnValue(defaultMutations);
    vi.mocked(useDeleteContact).mockReturnValue(defaultMutations);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('renders a loading skeleton', () => {
    vi.mocked(useContacts).mockReturnValue({ data: undefined, isLoading: true, error: null });
    const { container } = renderPage(<CustomerDirectory />);
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('renders an error message', () => {
    vi.mocked(useContacts).mockReturnValue({ data: undefined, isLoading: false, error: new Error('boom') });
    renderPage(<CustomerDirectory />);
    expect(screen.getByText('Failed to load customers')).toBeInTheDocument();
  });

  it('renders customer cards from mock data', () => {
    renderPage(<CustomerDirectory />);
    expect(screen.getByText('Customers')).toBeInTheDocument();
    expect(screen.getByText('Sarah Johnson')).toBeInTheDocument();
    expect(screen.getByText('David Smith')).toBeInTheDocument();
  });

  it('filters customers by search term', async () => {
    const user = userEvent.setup();
    renderPage(<CustomerDirectory />);

    const searchInput = screen.getByPlaceholderText(/search customers/i);
    await user.type(searchInput, 'Emma');

    expect(screen.getByText('Emma Wilson')).toBeInTheDocument();
    expect(screen.queryByText('Sarah Johnson')).not.toBeInTheDocument();
  });

  it('looks up addresses by postcode and fills address on selection', async () => {
    const user = userEvent.setup();
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          suggestions: [
            {
              id: 'addr-1',
              address: '7 Hylton Drive, Cheadle Hulme, Cheadle',
              url: '/get/addr-1',
            },
            {
              id: 'addr-2',
              address: '9 Hylton Drive, Cheadle Hulme, Cheadle',
              url: '/get/addr-2',
            },
          ],
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          postcode: 'SK8 7DH',
          formatted_address: ['7 Hylton Drive', 'Cheadle Hulme', 'Cheadle'],
        }),
      } as Response);

    renderPage(<CustomerDirectory />);
    await user.click(screen.getByRole('button', { name: /add customer/i }));

    const postcodeInput = screen.getByPlaceholderText(/postcode/i);
    await user.type(postcodeInput, 'SK87DH');
    await user.click(screen.getByRole('button', { name: /find address by postcode/i }));

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('api.getAddress.io/autocomplete/SK8%207DH?api-key=test-key'),
    );

    const addressResults = await screen.findByLabelText(/address search results/i);
    await user.selectOptions(addressResults, '7 Hylton Drive, Cheadle Hulme, Cheadle');

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('api.getAddress.io/v2/private-address/addr-1?api-key=test-key'),
    );
    expect(screen.getByPlaceholderText(/address/i)).toHaveValue('7 Hylton Drive, Cheadle Hulme, Cheadle');
  });

  it('does not fall back to nominatim when getAddress returns 404', async () => {
    const user = userEvent.setup();
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ Message: 'Postcode not found' }),
    } as Response);

    renderPage(<CustomerDirectory />);
    await user.click(screen.getByRole('button', { name: /add customer/i }));

    await user.type(screen.getByPlaceholderText(/postcode/i), 'SK87DH');
    await user.click(screen.getByRole('button', { name: /find address by postcode/i }));

    expect(await screen.findByText(/no matching addresses found for this postcode/i)).toBeInTheDocument();
    const requestedUrls = fetchSpy.mock.calls
      .map(([input]) => (typeof input === 'string' ? input : input instanceof URL ? input.toString() : String(input)));

    expect(requestedUrls.some((url) => url.includes('api.getAddress.io/autocomplete/SK8%207DH?api-key=test-key'))).toBe(true);
    expect(requestedUrls.some((url) => url.includes('nominatim.openstreetmap.org/search'))).toBe(false);
  });
});
