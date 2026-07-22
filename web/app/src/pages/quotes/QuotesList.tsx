import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Plus, Search, Sparkles, Send, XCircle, Trash2, X, Wand2 } from 'lucide-react';
import { useQuotes, useCreateQuote, useSendQuote, useRejectQuote, useDeleteQuote, useGenerateQuote } from '@/lib/api/hooks';
import { useUiStore } from '@/stores/uiStore';
import { StatusPill } from '@/components/shared/StatusPill';
import { toast } from 'sonner';
import { useContacts } from '@/lib/api/hooks';

export function QuotesList() {
  const setPageTitle = useUiStore(s => s.setPageTitle);
  const { data: quotes, isLoading, error } = useQuotes();
  const { data: contacts } = useContacts();
  const createQuote = useCreateQuote();
  const sendQuote = useSendQuote();
  const rejectQuote = useRejectQuote();
  const deleteQuote = useDeleteQuote();
  const generateQuote = useGenerateQuote();
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [isAiDialogOpen, setIsAiDialogOpen] = useState(false);

  useEffect(() => {
    setPageTitle('Quotes');
  }, [setPageTitle]);

  const filtered = (quotes ?? []).filter(q => {
    const matchesSearch = !search || q.reference.toLowerCase().includes(search.toLowerCase()) ||
      `${q.customer.firstName} ${q.customer.lastName}`.toLowerCase().includes(search.toLowerCase()) ||
      q.serviceType.toLowerCase().includes(search.toLowerCase());
    const matchesStatus = statusFilter === 'all' || q.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const handleCreate = (payload: {
    customerId: string;
    reference: string;
    serviceType: string;
    propertyAddress: string;
    lineItems: { description: string; quantity: number; unit: string; unitPrice: number }[];
  }) => {
    const subtotal = payload.lineItems.reduce((s, item) => s + item.quantity * item.unitPrice, 0);
    const vatRate = 20;
    const vatAmount = Math.round(subtotal * (vatRate / 100));
    const total = subtotal + vatAmount;
    createQuote.mutate(
      {
        ...payload,
        status: 'draft',
        lineItems: payload.lineItems.map((item, i) => ({
          id: `li-${Date.now()}-${i}`,
          ...item,
          total: item.quantity * item.unitPrice,
          isAiSuggested: false,
        })),
        subtotal,
        vatRate,
        vatAmount,
        total,
        aiGenerated: false,
        aiConfidenceScore: null,
        customerMessage: null,
        internalNotes: null,
        expiresAt: null,
      },
      {
        onSuccess: () => {
          toast.success('Quote created');
          setIsDialogOpen(false);
        },
        onError: (err) => toast.error(err.message || 'Failed to create quote'),
      }
    );
  };

  const handleSend = (id: string) => {
    sendQuote.mutate(id, {
      onSuccess: () => toast.success('Quote sent'),
      onError: (err) => toast.error(err.message || 'Failed to send quote'),
    });
  };

  const handleReject = (id: string) => {
    rejectQuote.mutate(id, {
      onSuccess: () => toast.success('Quote rejected'),
      onError: (err) => toast.error(err.message || 'Failed to reject quote'),
    });
  };

  const handleDelete = (id: string) => {
    if (!confirm('Delete this quote?')) return;
    deleteQuote.mutate(id, {
      onSuccess: () => toast.success('Quote deleted'),
      onError: (err) => toast.error(err.message || 'Failed to delete quote'),
    });
  };

  if (isLoading && !quotes) {
    return <div className="bg-white rounded-xl border border-[#E7E5E4] p-8 animate-pulse h-96" />;
  }

  if (error) return <div className="text-center py-12 text-[#DC2626]">Failed to load quotes</div>;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h1 className="text-xl font-semibold text-[#1C1917]">Quotes</h1>
          <span className="px-2 py-0.5 bg-[#F5F4F0] rounded-full text-xs font-medium text-[#57534E]">{filtered.length}</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            data-testid="generate-ai-quote"
            onClick={() => setIsAiDialogOpen(true)}
            className="h-9 px-4 flex items-center gap-2 rounded-lg bg-[#7C3AED] text-white text-xs font-semibold uppercase tracking-[0.05em] hover:bg-[#6D28D9] transition-colors"
          >
            <Wand2 className="w-4 h-4" />
            Generate with AI
          </button>
          <button
            onClick={() => setIsDialogOpen(true)}
            className="h-9 px-4 flex items-center gap-2 rounded-lg bg-[#D4650A] text-white text-xs font-semibold uppercase tracking-[0.05em] hover:bg-[#B85500] transition-colors"
          >
            <Plus className="w-4 h-4" />
            New Quote
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl border border-[#E7E5E4] p-3 flex items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#A8A29E]" />
          <input
            type="text" placeholder="Search quotes or customers..."
            value={search} onChange={e => setSearch(e.target.value)}
            className="w-full h-9 pl-9 pr-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A] focus:ring-2 focus:ring-[#FFF7ED] transition-all"
          />
        </div>
        <select
          value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
          className="h-9 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A] bg-white"
        >
          <option value="all">All Status</option>
          <option value="draft">Draft</option>
          <option value="sent">Sent</option>
          <option value="accepted">Accepted</option>
          <option value="rejected">Rejected</option>
          <option value="expired">Expired</option>
        </select>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-[#E7E5E4] shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="bg-[#F5F4F0]">
                <th className="text-left px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.05em] text-[#78716C]">Reference</th>
                <th className="text-left px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.05em] text-[#78716C]">Customer</th>
                <th className="text-left px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.05em] text-[#78716C]">Service</th>
                <th className="text-right px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.05em] text-[#78716C]">Value</th>
                <th className="text-left px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.05em] text-[#78716C]">Status</th>
                <th className="text-left px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.05em] text-[#78716C]">Date</th>
                <th className="text-center px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.05em] text-[#78716C]">AI</th>
                <th className="text-center px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.05em] text-[#78716C]">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((quote) => (
                <tr key={quote.id} className="border-t border-[#F0EFEA] hover:bg-[#F5F4F0] transition-colors cursor-pointer">
                  <td className="px-4 py-3">
                    <Link to={`/quotes/${quote.id}`} className="font-mono text-sm text-[#1C1917] hover:text-[#D4650A] transition-colors">
                      {quote.reference}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      {quote.customer.avatarUrl ? (
                        <img src={quote.customer.avatarUrl} alt="" className="w-7 h-7 rounded-full object-cover" />
                      ) : (
                        <div className="w-7 h-7 rounded-full bg-[#F5F4F0] flex items-center justify-center text-[11px] font-semibold text-[#57534E]">
                          {quote.customer.firstName[0]}{quote.customer.lastName[0]}
                        </div>
                      )}
                      <div>
                        <div className="text-sm font-medium text-[#1C1917]">{quote.customer.firstName} {quote.customer.lastName}</div>
                        <div className="text-[11px] text-[#A8A29E]">{quote.customer.phone}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm text-[#57534E]">{quote.serviceType}</td>
                  <td className="px-4 py-3 text-sm font-semibold text-[#1C1917] text-right">£{quote.total.toLocaleString()}</td>
                  <td className="px-4 py-3"><StatusPill status={quote.status} /></td>
                  <td className="px-4 py-3 text-xs text-[#78716C]">{new Date(quote.createdAt).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}</td>
                  <td className="px-4 py-3 text-center">
                    {quote.aiGenerated ? <Sparkles className="w-4 h-4 text-[#7C3AED] mx-auto" /> : <span className="text-[#A8A29E]">—</span>}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-center gap-1">
                      {quote.status === 'draft' && (
                        <button onClick={() => handleSend(quote.id)} title="Send" className="p-1.5 hover:bg-[#EFF6FF] rounded text-[#2563EB]"><Send className="w-3.5 h-3.5" /></button>
                      )}
                      {(quote.status === 'draft' || quote.status === 'sent') && (
                        <button onClick={() => handleReject(quote.id)} title="Reject" className="p-1.5 hover:bg-[#FEF2F2] rounded text-[#DC2626]"><XCircle className="w-3.5 h-3.5" /></button>
                      )}
                      <button onClick={() => handleDelete(quote.id)} title="Delete" className="p-1.5 hover:bg-[#FEF2F2] rounded text-[#DC2626]"><Trash2 className="w-3.5 h-3.5" /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {filtered.length === 0 && (
          <div className="py-12 text-center text-sm text-[#A8A29E]">No quotes found</div>
        )}
      </div>

      {isDialogOpen && <QuoteDialog contacts={contacts ?? []} onClose={() => setIsDialogOpen(false)} onSubmit={handleCreate} isSubmitting={createQuote.isPending} />}
      {isAiDialogOpen && (
        <AiQuoteDialog
          contacts={contacts ?? []}
          onClose={() => setIsAiDialogOpen(false)}
          onSubmit={(payload) =>
            generateQuote.mutate(payload, {
              onSuccess: (quote) => {
                toast.success('AI draft generated');
                setIsAiDialogOpen(false);
                navigate(`/quotes/${quote.id}`);
              },
              onError: (err) => toast.error(err.message || 'Failed to generate quote'),
            })
          }
          isSubmitting={generateQuote.isPending}
        />
      )}
    </div>
  );
}

function QuoteDialog({
  contacts,
  onClose,
  onSubmit,
  isSubmitting,
}: {
  contacts: { id: string; firstName: string; lastName: string }[];
  onClose: () => void;
  onSubmit: (payload: {
    customerId: string;
    reference: string;
    serviceType: string;
    propertyAddress: string;
    lineItems: { description: string; quantity: number; unit: string; unitPrice: number }[];
  }) => void;
  isSubmitting: boolean;
}) {
  const [customerId, setCustomerId] = useState('');
  const [reference, setReference] = useState('');
  const [serviceType, setServiceType] = useState('');
  const [propertyAddress, setPropertyAddress] = useState('');
  const [description, setDescription] = useState('');
  const [quantity, setQuantity] = useState(1);
  const [unit, setUnit] = useState('item');
  const [unitPrice, setUnitPrice] = useState(0);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-md p-6 space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-[#1C1917]">New Quote</h3>
          <button onClick={onClose} className="text-[#A8A29E] hover:text-[#1C1917]"><X className="w-5 h-5" /></button>
        </div>
        <div className="space-y-3">
          <div>
            <label className="block text-[11px] font-semibold uppercase text-[#78716C] mb-1">Customer</label>
            <select value={customerId} onChange={e => setCustomerId(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]">
              <option value="">Select customer</option>
              {contacts.map(c => <option key={c.id} value={c.id}>{c.firstName} {c.lastName}</option>)}
            </select>
          </div>
          <input placeholder="Reference" value={reference} onChange={e => setReference(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          <input placeholder="Service type" value={serviceType} onChange={e => setServiceType(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          <input placeholder="Property address" value={propertyAddress} onChange={e => setPropertyAddress(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          <div>
            <label className="block text-[11px] font-semibold uppercase text-[#78716C] mb-1">Line Item</label>
            <input placeholder="Description" value={description} onChange={e => setDescription(e.target.value)} className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A] mb-2" />
            <div className="grid grid-cols-3 gap-2">
              <input type="number" min={1} value={quantity} onChange={e => setQuantity(Number(e.target.value))} className="h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
              <input placeholder="Unit" value={unit} onChange={e => setUnit(e.target.value)} className="h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
              <input type="number" min={0} value={unitPrice} onChange={e => setUnitPrice(Number(e.target.value))} className="h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="h-9 px-4 text-sm font-medium text-[#57534E] hover:bg-[#F5F4F0] rounded-lg">Cancel</button>
          <button
            disabled={isSubmitting || !customerId || !reference || !serviceType}
            onClick={() => onSubmit({ customerId, reference, serviceType, propertyAddress, lineItems: [{ description, quantity, unit, unitPrice }] })}
            className="h-9 px-4 text-sm font-semibold bg-[#D4650A] text-white rounded-lg hover:bg-[#B85500] disabled:opacity-50"
          >
            {isSubmitting ? 'Saving...' : 'Create Quote'}
          </button>
        </div>
      </div>
    </div>
  );
}


interface AiQuoteDialogProps {
  contacts: { id: string; firstName: string; lastName: string }[];
  onClose: () => void;
  onSubmit: (payload: {
    contactId?: string;
    customerName?: string;
    customerEmail?: string;
    customerPhone?: string;
    description: string;
    propertyType?: string;
    useOcerp?: boolean;
  }) => void;
  isSubmitting: boolean;
}

function AiQuoteDialog({ contacts, onClose, onSubmit, isSubmitting }: AiQuoteDialogProps) {
  const [mode, setMode] = useState<'existing' | 'new'>('existing');
  const [contactId, setContactId] = useState('');
  const [customerName, setCustomerName] = useState('');
  const [customerEmail, setCustomerEmail] = useState('');
  const [customerPhone, setCustomerPhone] = useState('');
  const [description, setDescription] = useState('');
  const [propertyType, setPropertyType] = useState('house');
  const [useOcerp, setUseOcerp] = useState(true);

  const canSubmit =
    description.trim().length >= 5 &&
    (mode === 'existing' ? contactId : customerName.trim());

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-lg p-6 space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Wand2 className="w-5 h-5 text-[#7C3AED]" />
            <h3 className="text-lg font-semibold text-[#1C1917]">Generate Quote with AI</h3>
          </div>
          <button onClick={onClose} className="text-[#A8A29E] hover:text-[#1C1917]">
            <X className="w-5 h-5" />
          </button>
        </div>

        <p className="text-sm text-[#78716C]">
          Describe the job in plain English. The AI will retrieve matching cost items and
          draft line items for you to review.
        </p>

        <div className="space-y-3">
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 text-sm text-[#1C1917]">
              <input
                type="radio"
                checked={mode === 'existing'}
                onChange={() => setMode('existing')}
              />
              Existing customer
            </label>
            <label className="flex items-center gap-2 text-sm text-[#1C1917]">
              <input
                type="radio"
                checked={mode === 'new'}
                onChange={() => setMode('new')}
              />
              New lead
            </label>
          </div>

          {mode === 'existing' ? (
            <div>
              <label className="block text-[11px] font-semibold uppercase text-[#78716C] mb-1">
                Customer
              </label>
              <select
                value={contactId}
                onChange={(e) => setContactId(e.target.value)}
                className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#7C3AED]"
              >
                <option value="">Select customer</option>
                {contacts.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.firstName} {c.lastName}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <div className="space-y-2">
              <input
                placeholder="Customer name"
                value={customerName}
                onChange={(e) => setCustomerName(e.target.value)}
                className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#7C3AED]"
              />
              <input
                placeholder="Email (optional)"
                value={customerEmail}
                onChange={(e) => setCustomerEmail(e.target.value)}
                className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#7C3AED]"
              />
              <input
                placeholder="Phone (optional)"
                value={customerPhone}
                onChange={(e) => setCustomerPhone(e.target.value)}
                className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#7C3AED]"
              />
            </div>
          )}

          <div>
            <label className="block text-[11px] font-semibold uppercase text-[#78716C] mb-1">
              Property type
            </label>
            <select
              value={propertyType}
              onChange={(e) => setPropertyType(e.target.value)}
              className="w-full h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#7C3AED]"
            >
              <option value="house">House</option>
              <option value="apartment">Apartment</option>
              <option value="commercial">Commercial</option>
            </select>
          </div>

          <label className="flex items-center gap-2 text-sm text-[#1C1917]">
            <input
              type="checkbox"
              checked={useOcerp}
              onChange={(e) => setUseOcerp(e.target.checked)}
              data-testid="use-ocerp"
            />
            Generate detailed Bill of Quantities (OpenConstructionERP)
          </label>

          <div>
            <label htmlFor="ai-job-description" className="block text-[11px] font-semibold uppercase text-[#78716C] mb-1">
              Job description
            </label>
            <textarea
              id="ai-job-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g. Replace a broken consumer unit and install 4 new double sockets in a 3-bedroom house"
              rows={4}
              className="w-full p-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#7C3AED] resize-none"
            />
          </div>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button
            onClick={onClose}
            className="h-9 px-4 text-sm font-medium text-[#57534E] hover:bg-[#F5F4F0] rounded-lg"
          >
            Cancel
          </button>
          <button
            disabled={isSubmitting || !canSubmit}
            onClick={() =>
              onSubmit(
                mode === 'existing'
                  ? { contactId, description, propertyType, useOcerp }
                  : { customerName, customerEmail, customerPhone, description, propertyType, useOcerp }
              )
            }
            className="h-9 px-4 text-sm font-semibold bg-[#7C3AED] text-white rounded-lg hover:bg-[#6D28D9] disabled:opacity-50 flex items-center gap-2"
          >
            {isSubmitting ? (
              'Generating...'
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                Generate draft
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
