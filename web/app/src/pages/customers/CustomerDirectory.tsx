import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Search, Phone, Mail, Star, Wrench, X } from 'lucide-react';
import { useContacts, useCreateContact, useDeleteContact } from '@/lib/api/hooks';
import { useUiStore } from '@/stores/uiStore';
import { toast } from 'sonner';
import type { SourceChannel } from '@/types';

const sourceChannels: SourceChannel[] = ['pwa', 'chatbot', 'voice', 'whatsapp', 'referral', 'manual'];

interface AddressLookupResult {
  display_name?: string;
}

interface AddressSuggestion {
  id: string;
  address: string;
  url?: string;
}

interface GetAddressAutocompleteResponse {
  suggestions?: AddressSuggestion[];
}

interface GetAddressDetailResponse {
  formatted_address?: string[];
  postcode?: string;
}

type GetAddressLookupStatus = 'ok' | 'no_results' | 'unavailable';

interface GetAddressLookupResult {
  suggestions: AddressSuggestion[];
  status: GetAddressLookupStatus;
}

function normalizePostcode(value: string): string {
  const compact = value.trim().replace(/\s+/g, '').toUpperCase();
  const ukPostcodeMatch = compact.match(/^([A-Z]{1,2}\d[A-Z\d]?)(\d[A-Z]{2})$/);
  if (ukPostcodeMatch) {
    return `${ukPostcodeMatch[1]} ${ukPostcodeMatch[2]}`;
  }
  return compact;
}

function sortAddressOptions(options: string[]): string[] {
  return options.slice().sort((a, b) => a.localeCompare(b, 'en-GB', { numeric: true }));
}

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('Address lookup timed out')), ms);
    promise
      .then((value) => {
        clearTimeout(timeout);
        resolve(value);
      })
      .catch((error) => {
        clearTimeout(timeout);
        reject(error);
      });
  });
}

async function fetchGetAddressAutocomplete(postcode: string): Promise<GetAddressLookupResult> {
  const apiKey = import.meta.env.VITE_GETADDRESS_IO_API_KEY as string | undefined;
  if (!apiKey || !apiKey.trim()) {
    return { suggestions: [], status: 'unavailable' };
  }

  const response = await withTimeout(
    fetch(
      `https://api.getAddress.io/autocomplete/${encodeURIComponent(postcode)}?api-key=${encodeURIComponent(apiKey.trim())}&all=true&top=6&show-postcode=true`,
    ),
    4500,
  );

  if (response.status === 404) {
    return { suggestions: [], status: 'no_results' };
  }

  if (!response.ok) {
    return { suggestions: [], status: 'unavailable' };
  }

  const data = (await response.json()) as GetAddressAutocompleteResponse;
  const suggestions = (data.suggestions ?? [])
    .filter((suggestion): suggestion is AddressSuggestion =>
      Boolean(suggestion?.id?.trim()) && Boolean(suggestion?.address?.trim()),
    )
    .map((suggestion) => ({
      id: suggestion.id.trim(),
      address: suggestion.address.trim(),
      url: suggestion.url,
    }));

  if (suggestions.length === 0) {
    return { suggestions: [], status: 'no_results' };
  }

  return {
    suggestions,
    status: 'ok',
  };
}

async function fetchGetAddressDetailsById(id: string): Promise<GetAddressDetailResponse | null> {
  const apiKey = import.meta.env.VITE_GETADDRESS_IO_API_KEY as string | undefined;
  if (!apiKey || !apiKey.trim()) {
    return null;
  }

  const privateAddressResponse = await withTimeout(
    fetch(
      `https://api.getAddress.io/v2/private-address/${encodeURIComponent(id)}?api-key=${encodeURIComponent(apiKey.trim())}`,
    ),
    4500,
  );

  if (privateAddressResponse.ok) {
    return (await privateAddressResponse.json()) as GetAddressDetailResponse;
  }

  const response = await withTimeout(
    fetch(`https://api.getAddress.io/get/${encodeURIComponent(id)}?api-key=${encodeURIComponent(apiKey.trim())}`),
    4500,
  );
  if (!response.ok) {
    return null;
  }

  return (await response.json()) as GetAddressDetailResponse;
}

export function CustomerDirectory() {
  const setPageTitle = useUiStore(s => s.setPageTitle);
  const { data: customers, isLoading, error } = useContacts();
  const createContact = useCreateContact();
  const deleteContact = useDeleteContact();
  const [search, setSearch] = useState('');
  const [isDialogOpen, setIsDialogOpen] = useState(false);

  useEffect(() => {
    setPageTitle('Customers');
  }, [setPageTitle]);

  const filtered = (customers ?? []).filter(c =>
    !search || `${c.firstName} ${c.lastName}`.toLowerCase().includes(search.toLowerCase()) || c.phone.includes(search)
  );

  const handleCreate = (payload: {
    firstName: string;
    lastName: string;
    email: string;
    phone: string;
    address: string;
    postcode: string;
    propertyType: 'house' | 'apartment' | 'commercial' | null;
    sourceChannel: SourceChannel;
  }) => {
    createContact.mutate(
      {
        ...payload,
        tenantId: 'tenant-1',
        lifetimeValue: 0,
        reviewCount: 0,
      },
      {
        onSuccess: () => {
          toast.success('Customer created');
          setIsDialogOpen(false);
        },
        onError: (err) => toast.error(err.message || 'Failed to create customer'),
      }
    );
  };

  const handleDelete = (id: string, name: string) => {
    if (!confirm(`Delete ${name}?`)) return;
    deleteContact.mutate(id, {
      onSuccess: () => toast.success('Customer deleted'),
      onError: (err) => toast.error(err.message || 'Failed to delete customer'),
    });
  };

  if (isLoading && !customers) return <div className="bg-white rounded-xl h-96 animate-pulse" />;
  if (error) return <div className="text-center py-12 text-[#DC2626]">Failed to load customers</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-xl font-semibold text-[#1C1917]">Customers</h2>
          <span className="px-2 py-0.5 bg-[#F5F4F0] rounded-full text-xs font-medium text-[#57534E]">{filtered.length}</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#A8A29E]" />
            <input type="text" placeholder="Search customers..." value={search} onChange={e => setSearch(e.target.value)}
              className="h-9 w-56 pl-9 pr-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          </div>
          <button
            onClick={() => setIsDialogOpen(true)}
            className="h-9 px-4 flex items-center gap-2 rounded-lg bg-[#D4650A] text-white text-xs font-semibold hover:bg-[#B85500] transition-colors"
          >
            <Plus className="w-4 h-4" /> Add Customer
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {filtered.map(customer => (
          <div key={customer.id} className="bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all duration-200">
            <Link to={`/customers/${customer.id}`} className="block">
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  {customer.avatarUrl ? (
                    <img src={customer.avatarUrl} alt="" className="w-12 h-12 rounded-full object-cover" />
                  ) : (
                    <div className="w-12 h-12 rounded-full bg-[#F5F4F0] flex items-center justify-center text-sm font-semibold text-[#57534E]">
                      {customer.firstName[0]}{customer.lastName[0]}
                    </div>
                  )}
                  <div>
                    <div className="text-base font-semibold text-[#1C1917]">{customer.firstName} {customer.lastName}</div>
                    <div className="text-xs text-[#78716C]">Since {new Date(customer.createdAt).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })}</div>
                  </div>
                </div>
              </div>
              <div className="space-y-1.5 mb-4">
                <div className="flex items-center gap-2 text-sm text-[#57534E]">
                  <Phone className="w-3.5 h-3.5 text-[#A8A29E]" /> {customer.phone}
                </div>
                {customer.email && (
                  <div className="flex items-center gap-2 text-sm text-[#57534E]">
                    <Mail className="w-3.5 h-3.5 text-[#A8A29E]" /> {customer.email}
                  </div>
                )}
              </div>
              <div className="flex items-center gap-4 pt-3 border-t border-[#F0EFEA]">
                <div className="flex items-center gap-1 text-xs text-[#78716C]">
                  <Wrench className="w-3.5 h-3.5" /> {customer.lifetimeValue > 0 ? `${Math.round(customer.lifetimeValue / 4000) + 1} Jobs` : 'New'}
                </div>
                <div className="flex items-center gap-1 text-xs text-[#78716C]">
                  £{(customer.lifetimeValue / 1000).toFixed(1)}k Lifetime
                </div>
                {customer.averageRating && (
                  <div className="flex items-center gap-1 text-xs text-[#D4650A]">
                    <Star className="w-3.5 h-3.5 fill-[#D4650A]" /> {customer.averageRating}
                  </div>
                )}
              </div>
            </Link>
            <div className="mt-3 pt-3 border-t border-[#F0EFEA] flex justify-end">
              <button
                onClick={() => handleDelete(customer.id, `${customer.firstName} ${customer.lastName}`)}
                className="text-xs text-[#DC2626] hover:underline"
              >
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>

      {isDialogOpen && <CustomerDialog onClose={() => setIsDialogOpen(false)} onSubmit={handleCreate} isSubmitting={createContact.isPending} />}
    </div>
  );
}

function CustomerDialog({
  onClose,
  onSubmit,
  isSubmitting,
}: {
  onClose: () => void;
  onSubmit: (payload: {
    firstName: string;
    lastName: string;
    email: string;
    phone: string;
    address: string;
    postcode: string;
    propertyType: 'house' | 'apartment' | 'commercial' | null;
    sourceChannel: SourceChannel;
  }) => void;
  isSubmitting: boolean;
}) {
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [address, setAddress] = useState('');
  const [postcode, setPostcode] = useState('');
  const [selectedAddressId, setSelectedAddressId] = useState('');
  const [addressSuggestions, setAddressSuggestions] = useState<AddressSuggestion[]>([]);
  const [addressOptions, setAddressOptions] = useState<string[]>([]);
  const [isLookupLoading, setIsLookupLoading] = useState(false);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [propertyType, setPropertyType] = useState<'house' | 'apartment' | 'commercial' | ''>('house');
  const [sourceChannel, setSourceChannel] = useState<SourceChannel>('manual');

  const handleLookupAddress = async () => {
    const normalizedPostcode = normalizePostcode(postcode);
    if (!normalizedPostcode) {
      setLookupError('Enter a postcode to find addresses');
      return;
    }

    setIsLookupLoading(true);
    setLookupError(null);
    try {
      const providerResult = await fetchGetAddressAutocomplete(normalizedPostcode);
      if (providerResult.suggestions.length > 0) {
        setAddressSuggestions(providerResult.suggestions);
        setAddressOptions(sortAddressOptions(providerResult.suggestions.map((suggestion) => suggestion.address)));
        setPostcode(normalizedPostcode);
        setSelectedAddressId('');
        return;
      }

      if (providerResult.status === 'no_results') {
        setLookupError('No matching addresses found for this postcode');
        setAddressSuggestions([]);
        setAddressOptions([]);
        setPostcode(normalizedPostcode);
        return;
      }

      const fallbackResponse = await withTimeout(
        fetch(
          `https://nominatim.openstreetmap.org/search?format=jsonv2&countrycodes=gb&q=${encodeURIComponent(normalizedPostcode)}&addressdetails=1&limit=12`,
          {
            headers: {
              Accept: 'application/json',
            },
          },
        ),
        3500,
      );

      if (!fallbackResponse.ok) {
        throw new Error(`Address lookup failed (${fallbackResponse.status})`);
      }

      const fallbackData = (await fallbackResponse.json()) as AddressLookupResult[];
      const fallbackOptions = Array.from(
        new Set(
          fallbackData
            .map((entry) => entry.display_name?.trim())
            .filter((entry): entry is string => Boolean(entry)),
        ),
      );

      if (fallbackOptions.length === 0) {
        setLookupError('No matching addresses found for this postcode');
        setAddressSuggestions([]);
        setAddressOptions([]);
        return;
      }

      setAddressSuggestions([]);
      setAddressOptions(sortAddressOptions(fallbackOptions));
      setPostcode(normalizedPostcode);
    } catch {
      setLookupError('Address lookup is unavailable. Enter address manually.');
      setAddressSuggestions([]);
      setAddressOptions([]);
    } finally {
      setIsLookupLoading(false);
    }
  };

  const handleAddressSelection = async (selectedValue: string) => {
    setAddress(selectedValue);

    const matchedSuggestion = addressSuggestions.find((suggestion) => suggestion.address === selectedValue);
    if (!matchedSuggestion) {
      setSelectedAddressId('');
      return;
    }

    setSelectedAddressId(matchedSuggestion.id);
    const details = await fetchGetAddressDetailsById(matchedSuggestion.id);
    if (!details) {
      return;
    }

    const formattedAddress = (details.formatted_address ?? [])
      .map((part) => part.trim())
      .filter(Boolean)
      .join(', ');
    if (formattedAddress) {
      setAddress(formattedAddress);
    }
    if (details.postcode) {
      setPostcode(normalizePostcode(details.postcode));
    }
  };

  const handlePostcodeChange = (value: string) => {
    setPostcode(value);
    setLookupError(null);
    setSelectedAddressId('');
    setAddressSuggestions([]);
    setAddressOptions([]);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-md p-6 space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-[#1C1917]">Add Customer</h3>
          <button onClick={onClose} className="text-[#A8A29E] hover:text-[#1C1917]"><X className="w-5 h-5" /></button>
        </div>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <input placeholder="First name" value={firstName} onChange={e => setFirstName(e.target.value)} className="h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
            <input placeholder="Last name" value={lastName} onChange={e => setLastName(e.target.value)} className="h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          </div>
          <input placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          <input placeholder="Phone" value={phone} onChange={e => setPhone(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          <input placeholder="Address" value={address} onChange={e => setAddress(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          <div className="grid grid-cols-[1fr_auto] gap-2">
            <input
              placeholder="Postcode"
              value={postcode}
              onChange={e => handlePostcodeChange(e.target.value)}
              className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]"
            />
            <button
              type="button"
              onClick={handleLookupAddress}
              disabled={isLookupLoading}
              className="h-10 px-3 text-xs font-semibold rounded-lg border border-[#E7E5E4] bg-[#F5F4F0] text-[#57534E] hover:bg-[#EFEEE9] disabled:opacity-50"
              aria-label="Find address by postcode"
            >
              {isLookupLoading ? 'Looking up...' : 'Find Address'}
            </button>
          </div>
          {addressOptions.length > 0 && (
            <select
              aria-label="Address search results"
              value={selectedAddressId ? addressSuggestions.find((suggestion) => suggestion.id === selectedAddressId)?.address ?? '' : ''}
              onChange={(e) => void handleAddressSelection(e.target.value)}
              className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]"
            >
              <option value="" disabled>Select an address</option>
              {addressOptions.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          )}
          {lookupError && <p className="text-xs text-[#DC2626]">{lookupError}</p>}
          <div className="grid grid-cols-2 gap-3">
            <select value={propertyType} onChange={e => setPropertyType(e.target.value as 'house' | 'apartment' | 'commercial')} className="h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]">
              <option value="house">House</option>
              <option value="apartment">Apartment</option>
              <option value="commercial">Commercial</option>
            </select>
            <select value={sourceChannel} onChange={e => setSourceChannel(e.target.value as SourceChannel)} className="h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]">
              {sourceChannels.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="h-9 px-4 text-sm font-medium text-[#57534E] hover:bg-[#F5F4F0] rounded-lg">Cancel</button>
          <button
            disabled={isSubmitting || !firstName || !lastName || !phone}
            onClick={() => onSubmit({ firstName, lastName, email, phone, address, postcode, propertyType: propertyType || null, sourceChannel })}
            className="h-9 px-4 text-sm font-semibold bg-[#D4650A] text-white rounded-lg hover:bg-[#B85500] disabled:opacity-50"
          >
            {isSubmitting ? 'Saving...' : 'Save Customer'}
          </button>
        </div>
      </div>
    </div>
  );
}
