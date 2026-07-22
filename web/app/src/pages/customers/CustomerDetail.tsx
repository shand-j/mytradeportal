import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Phone, Mail, MapPin, Star, FileText, Wrench, X } from 'lucide-react';
import { useContact, useUpdateContact, useQuotes, useJobs, useInvoices } from '@/lib/api/hooks';
import { useUiStore } from '@/stores/uiStore';
import { toast } from 'sonner';
import type { SourceChannel } from '@/types';

const sourceChannels: SourceChannel[] = ['pwa', 'chatbot', 'voice', 'whatsapp', 'referral', 'manual'];

export function CustomerDetail() {
  const { id = '' } = useParams<{ id: string }>();
  const setPageTitle = useUiStore(s => s.setPageTitle);
  const { data: customer, isLoading, error } = useContact(id);
  const { data: allQuotes } = useQuotes();
  const { data: allJobs } = useJobs();
  const { data: allInvoices } = useInvoices();
  const updateContact = useUpdateContact();
  const [isEditing, setIsEditing] = useState(false);

  useEffect(() => {
    setPageTitle('Customer Detail');
  }, [setPageTitle]);

  if (isLoading) return <div className="bg-white rounded-xl h-96 animate-pulse" />;
  if (error || !customer) return <div className="text-center py-12 text-[#A8A29E]">Customer not found</div>;

  const customerJobs = (allJobs ?? []).filter(j => j.customerId === id);
  const customerQuotes = (allQuotes ?? []).filter(q => q.customerId === id);
  const customerInvoices = (allInvoices ?? []).filter(i => i.customerId === id);

  const handleUpdate = (data: Partial<typeof customer>) => {
    updateContact.mutate(
      { id, data },
      {
        onSuccess: () => {
          toast.success('Customer updated');
          setIsEditing(false);
        },
        onError: (err) => toast.error(err.message || 'Failed to update customer'),
      }
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm">
        <Link to="/customers" className="text-[#78716C] hover:text-[#D4650A]">Customers</Link>
        <span className="text-[#A8A29E]">/</span>
        <span className="text-[#1C1917]">{customer.firstName} {customer.lastName}</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          <div className="bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm">
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-start gap-4">
                {customer.avatarUrl ? (
                  <img src={customer.avatarUrl} alt="" className="w-16 h-16 rounded-full object-cover" />
                ) : (
                  <div className="w-16 h-16 rounded-full bg-[#F5F4F0] flex items-center justify-center text-lg font-semibold text-[#57534E]">
                    {customer.firstName[0]}{customer.lastName[0]}
                  </div>
                )}
                <div className="flex-1">
                  <h2 className="text-xl font-semibold text-[#1C1917]">{customer.firstName} {customer.lastName}</h2>
                  <div className="flex items-center gap-1 mt-1">
                    {customer.averageRating && (
                      <>
                        <Star className="w-4 h-4 text-amber-400 fill-amber-400" />
                        <span className="text-sm font-medium text-[#1C1917]">{customer.averageRating}</span>
                        <span className="text-xs text-[#78716C]">({customer.reviewCount} reviews)</span>
                      </>
                    )}
                  </div>
                </div>
              </div>
              <button
                onClick={() => setIsEditing(true)}
                className="text-xs text-[#D4650A] hover:underline"
              >
                Edit
              </button>
            </div>
            <div className="grid grid-cols-2 gap-3 pt-4 border-t border-[#F0EFEA]">
              <div className="flex items-center gap-2 text-sm text-[#57534E]"><Phone className="w-4 h-4 text-[#A8A29E]" /> {customer.phone}</div>
              {customer.email && <div className="flex items-center gap-2 text-sm text-[#57534E]"><Mail className="w-4 h-4 text-[#A8A29E]" /> {customer.email}</div>}
              {customer.address && <div className="flex items-center gap-2 text-sm text-[#57534E] col-span-2"><MapPin className="w-4 h-4 text-[#A8A29E]" /> {customer.address}</div>}
            </div>
          </div>

          {/* Quotes */}
          <div className="bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-[#1C1917] mb-3 uppercase tracking-[0.05em]">Quotes ({customerQuotes.length})</h3>
            <div className="space-y-2">
              {customerQuotes.map(q => (
                <Link key={q.id} to={`/quotes/${q.id}`} className="flex items-center justify-between py-2 border-b border-[#F0EFEA] last:border-0 hover:bg-[#F5F4F0] px-2 -mx-2 rounded transition-colors">
                  <div className="flex items-center gap-2">
                    <FileText className="w-4 h-4 text-[#A8A29E]" />
                    <span className="font-mono text-sm text-[#1C1917]">{q.reference}</span>
                    <span className="text-xs text-[#78716C]">{q.serviceType}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-medium text-[#1C1917]">£{q.total.toLocaleString()}</span>
                    <span className={`text-[11px] font-semibold uppercase ${q.status === 'accepted' ? 'text-[#16A34A]' : q.status === 'sent' ? 'text-[#2563EB]' : 'text-[#78716C]'}`}>{q.status}</span>
                  </div>
                </Link>
              ))}
              {customerQuotes.length === 0 && <div className="text-xs text-[#A8A29E]">No quotes</div>}
            </div>
          </div>

          {/* Jobs */}
          <div className="bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-[#1C1917] mb-3 uppercase tracking-[0.05em]">Jobs ({customerJobs.length})</h3>
            <div className="space-y-2">
              {customerJobs.map(j => (
                <Link key={j.id} to={`/jobs/${j.id}`} className="flex items-center justify-between py-2 border-b border-[#F0EFEA] last:border-0 hover:bg-[#F5F4F0] px-2 -mx-2 rounded transition-colors">
                  <div className="flex items-center gap-2">
                    <Wrench className="w-4 h-4 text-[#A8A29E]" />
                    <span className="font-mono text-sm text-[#1C1917]">{j.reference}</span>
                    <span className="text-xs text-[#78716C]">{j.serviceType}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-medium text-[#1C1917]">£{j.value.toLocaleString()}</span>
                    <span className={`text-[11px] font-semibold uppercase ${j.status === 'completed' ? 'text-[#16A34A]' : 'text-[#78716C]'}`}>{j.status.replace(/_/g, ' ')}</span>
                  </div>
                </Link>
              ))}
              {customerJobs.length === 0 && <div className="text-xs text-[#A8A29E]">No jobs</div>}
            </div>
          </div>

          {/* Invoices */}
          <div className="bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-[#1C1917] mb-3 uppercase tracking-[0.05em]">Invoices ({customerInvoices.length})</h3>
            <div className="space-y-2">
              {customerInvoices.map(inv => (
                <Link key={inv.id} to={`/invoices/${inv.id}`} className="flex items-center justify-between py-2 border-b border-[#F0EFEA] last:border-0 hover:bg-[#F5F4F0] px-2 -mx-2 rounded transition-colors">
                  <div className="flex items-center gap-2">
                    <FileText className="w-4 h-4 text-[#A8A29E]" />
                    <span className="font-mono text-sm text-[#1C1917]">{inv.reference}</span>
                    <span className="text-xs text-[#78716C]">{new Date(inv.issueDate).toLocaleDateString('en-GB')}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-medium text-[#1C1917]">£{inv.total.toLocaleString()}</span>
                    <span className={`text-[11px] font-semibold uppercase ${inv.status === 'paid' ? 'text-[#16A34A]' : inv.status === 'overdue' ? 'text-[#DC2626]' : 'text-[#78716C]'}`}>{inv.status}</span>
                  </div>
                </Link>
              ))}
              {customerInvoices.length === 0 && <div className="text-xs text-[#A8A29E]">No invoices</div>}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-[#1C1917] mb-3 uppercase tracking-[0.05em]">Quick Actions</h3>
            <div className="space-y-2">
              <Link to="/quotes" className="w-full h-10 flex items-center justify-center gap-2 rounded-lg bg-[#D4650A] text-white text-xs font-semibold hover:bg-[#B85500] transition-colors">
                <FileText className="w-4 h-4" /> New Quote
              </Link>
              <button className="w-full h-10 flex items-center justify-center gap-2 rounded-lg bg-[#F5F4F0] border border-[#E7E5E4] text-[#1C1917] text-xs font-semibold hover:bg-[#EFEEE9] transition-colors">
                <Wrench className="w-4 h-4" /> Schedule Job
              </button>
              <button className="w-full h-10 flex items-center justify-center gap-2 rounded-lg bg-[#F5F4F0] border border-[#E7E5E4] text-[#1C1917] text-xs font-semibold hover:bg-[#EFEEE9] transition-colors">
                <Phone className="w-4 h-4" /> Log Call
              </button>
            </div>
          </div>

          <div className="bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-[#1C1917] mb-3 uppercase tracking-[0.05em]">Stats</h3>
            <div className="space-y-3">
              <div className="flex justify-between text-sm"><span className="text-[#57534E]">Total Spent</span><span className="font-semibold text-[#1C1917]">£{customer.lifetimeValue.toLocaleString()}</span></div>
              <div className="flex justify-between text-sm"><span className="text-[#57534E]">Jobs Completed</span><span className="font-semibold text-[#1C1917]">{customerJobs.filter(j => j.status === 'completed').length}</span></div>
              <div className="flex justify-between text-sm"><span className="text-[#57534E]">Avg Job Value</span><span className="font-semibold text-[#1C1917]">£{customerJobs.length > 0 ? Math.round(customer.lifetimeValue / customerJobs.length).toLocaleString() : '0'}</span></div>
            </div>
          </div>
        </div>
      </div>

      {isEditing && <CustomerEditDialog customer={customer} onClose={() => setIsEditing(false)} onSubmit={handleUpdate} isSubmitting={updateContact.isPending} />}
    </div>
  );
}

function CustomerEditDialog({
  customer,
  onClose,
  onSubmit,
  isSubmitting,
}: {
  customer: {
    firstName: string;
    lastName: string;
    email: string | null;
    phone: string;
    address: string | null;
    postcode: string | null;
    propertyType: 'house' | 'apartment' | 'commercial' | null;
    sourceChannel: SourceChannel;
  };
  onClose: () => void;
  onSubmit: (data: Partial<typeof customer>) => void;
  isSubmitting: boolean;
}) {
  const [firstName, setFirstName] = useState(customer.firstName);
  const [lastName, setLastName] = useState(customer.lastName);
  const [email, setEmail] = useState(customer.email ?? '');
  const [phone, setPhone] = useState(customer.phone);
  const [address, setAddress] = useState(customer.address ?? '');
  const [postcode, setPostcode] = useState(customer.postcode ?? '');
  const [propertyType, setPropertyType] = useState<'house' | 'apartment' | 'commercial' | ''>(customer.propertyType ?? 'house');
  const [sourceChannel, setSourceChannel] = useState<SourceChannel>(customer.sourceChannel);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-md p-6 space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-[#1C1917]">Edit Customer</h3>
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
            onClick={() => onSubmit({ firstName, lastName, email: email || null, phone, address: address || null, postcode: postcode || null, propertyType: propertyType || null, sourceChannel })}
            className="h-9 px-4 text-sm font-semibold bg-[#D4650A] text-white rounded-lg hover:bg-[#B85500] disabled:opacity-50"
          >
            {isSubmitting ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  );
}
