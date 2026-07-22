import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Search, Phone, Mail, Star, Wrench, X } from 'lucide-react';
import { useContacts, useCreateContact, useDeleteContact } from '@/lib/api/hooks';
import { useUiStore } from '@/stores/uiStore';
import { toast } from 'sonner';
import type { SourceChannel } from '@/types';

const sourceChannels: SourceChannel[] = ['pwa', 'chatbot', 'voice', 'whatsapp', 'referral', 'manual'];

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
  const [propertyType, setPropertyType] = useState<'house' | 'apartment' | 'commercial' | ''>('house');
  const [sourceChannel, setSourceChannel] = useState<SourceChannel>('manual');

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
          <input placeholder="Postcode" value={postcode} onChange={e => setPostcode(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
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
