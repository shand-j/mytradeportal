import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { CustomerDirectory } from './CustomerDirectory';
import { api } from '@/lib/api/client';
import { useContacts, useCreateContact, useDeleteContact } from '@/lib/api/hooks';
import { renderPage, resetStores } from '@/test/test-utils';
import { mockCustomers } from '@/lib/mock/data/customers';
import { toCustomer } from '@/lib/api/hooks/contacts';

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
    vi.clearAllMocks();
    resetStores();
    vi.mocked(useContacts).mockReturnValue({ data: mockCustomers, isLoading: false, error: null });
    vi.mocked(useCreateContact).mockReturnValue(defaultMutations);
    vi.mocked(useDeleteContact).mockReturnValue(defaultMutations);
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
    const apiGetSpy = vi
      .spyOn(api, 'get')
      .mockResolvedValueOnce({
        status: 'ok',
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
      })
      .mockResolvedValueOnce({
        postcode: 'SK8 7DH',
        formattedAddress: ['7 Hylton Drive', 'Cheadle Hulme', 'Cheadle'],
      });

    renderPage(<CustomerDirectory />);
    await user.click(screen.getByRole('button', { name: /add customer/i }));

    const postcodeInput = screen.getByPlaceholderText(/postcode/i);
    await user.type(postcodeInput, 'SK87DH');
    await user.click(screen.getByRole('button', { name: /find address by postcode/i }));

    expect(apiGetSpy).toHaveBeenCalledTimes(1);
    expect(apiGetSpy).toHaveBeenCalledWith(
      '/integrations/address/autocomplete?postcode=SK8%207DH',
    );

    const addressResults = await screen.findByLabelText(/address search results/i);
    await user.selectOptions(addressResults, '7 Hylton Drive, Cheadle Hulme, Cheadle');

    expect(apiGetSpy).toHaveBeenCalledWith('/integrations/address/private-address/addr-1');
    expect(screen.getByPlaceholderText(/address/i)).toHaveValue('7 Hylton Drive, Cheadle Hulme, Cheadle');
  });

  it('does not fall back to nominatim when getAddress returns 404', async () => {
    const user = userEvent.setup();
    const apiGetSpy = vi.spyOn(api, 'get').mockResolvedValue({
      status: 'no_results',
      suggestions: [],
    });
    const fetchSpy = vi.spyOn(globalThis, 'fetch');

    renderPage(<CustomerDirectory />);
    await user.click(screen.getByRole('button', { name: /add customer/i }));

    await user.type(screen.getByPlaceholderText(/postcode/i), 'SK87DH');
    await user.click(screen.getByRole('button', { name: /find address by postcode/i }));

    expect(await screen.findByText(/no matching addresses found for this postcode/i)).toBeInTheDocument();
    const requestedPaths = apiGetSpy.mock.calls.map(([path]) => String(path));
    expect(requestedPaths).toContain('/integrations/address/autocomplete?postcode=SK8%207DH');

    const requestedUrls = fetchSpy.mock.calls.map(([input]) =>
      typeof input === 'string' ? input : input instanceof URL ? input.toString() : String(input),
    );
    expect(requestedUrls.some((url) => url.includes('nominatim.openstreetmap.org/search'))).toBe(false);
  });

  it('guards duplicate Save Customer activation', async () => {
    const user = userEvent.setup();
    renderPage(<CustomerDirectory />);
    await user.click(screen.getByRole('button', { name: /add customer/i }));

    await user.type(screen.getByPlaceholderText(/first name/i), 'Mary Jane');
    await user.type(screen.getByPlaceholderText(/last name/i), 'Smith');
    await user.type(screen.getByPlaceholderText(/email/i), 'mary@example.com');
    await user.type(screen.getByPlaceholderText(/phone/i), '07700 900000');

    const save = screen.getByRole('button', { name: /save customer/i });
    await user.dblClick(save);

    expect(defaultMutations.mutate).toHaveBeenCalledTimes(1);
  });

  it('rejects malformed email inline', async () => {
    const user = userEvent.setup();
    renderPage(<CustomerDirectory />);
    await user.click(screen.getByRole('button', { name: /add customer/i }));

    await user.type(screen.getByPlaceholderText(/first name/i), 'José');
    await user.type(screen.getByPlaceholderText(/last name/i), 'O’Neill');
    await user.type(screen.getByPlaceholderText(/phone/i), '07700 900000');
    await user.type(screen.getByPlaceholderText(/email/i), 'not-an-email');

    expect(screen.getByRole('alert')).toHaveTextContent(/valid email address/i);
    expect(screen.getByRole('button', { name: /save customer/i })).toBeDisabled();
  });

  it('preserves the canonical name and Unicode/emoji display text', () => {
    const customer = toCustomer({
      id: 'c-1',
      name: 'Mary Jane 😀 Smith',
      email: null,
      phone: '',
      address: null,
      postcode: null,
      createdAt: '2026-11-21',
    });

    expect(customer.firstName).toBe('Mary');
    expect(customer.lastName).toBe('Jane 😀 Smith');
    expect(`${customer.firstName} ${customer.lastName}`.trim()).toBe('Mary Jane 😀 Smith');

    const singleName = toCustomer({ id: 'c-2', name: 'Prince', createdAt: '2026-11-21' });
    expect(`${singleName.firstName} ${singleName.lastName}`.trim()).toBe('Prince');
  });
});
