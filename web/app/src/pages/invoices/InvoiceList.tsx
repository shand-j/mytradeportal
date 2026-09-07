import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Search, AlertTriangle, Send, X } from 'lucide-react';
import { useInvoices, useCreateInvoice, useSendInvoice } from '@/lib/api/hooks';
import { useContacts } from '@/lib/api/hooks';
import { useUiStore } from '@/stores/uiStore';
import { StatusPill } from '@/components/shared/StatusPill';
import { formatGBP } from '@/lib/utils';
import { toast } from 'sonner';

export function InvoiceList() {
  const setPageTitle = useUiStore(s => s.setPageTitle);
  const { data: invoices, isLoading, error } = useInvoices();
  const { data: contacts } = useContacts();
  const createInvoice = useCreateInvoice();
  const sendInvoice = useSendInvoice();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [isDialogOpen, setIsDialogOpen] = useState(false);

  useEffect(() => {
    setPageTitle('Invoices');
  }, [setPageTitle]);

  const filtered = (invoices ?? []).filter(i => {
    const matchesSearch = !search || i.reference.toLowerCase().includes(search.toLowerCase()) || `${i.customer.firstName} ${i.customer.lastName}`.toLowerCase().includes(search.toLowerCase());
    const matchesStatus = statusFilter === 'all' || i.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const totalPaid = (invoices ?? []).filter(i => i.status === 'paid').reduce((s, i) => s + i.total, 0);
  const totalOutstanding = (invoices ?? []).filter(i => ['sent', 'viewed', 'overdue'].includes(i.status)).reduce((s, i) => s + i.amountDue, 0);
  const overdueCount = (invoices ?? []).filter(i => i.status === 'overdue').length;

  const handleCreate = (payload: {
    customerId: string;
    reference: string;
    issueDate: string;
    dueDate: string;
    lineItems: { description: string; quantity: number; unit: string; unitPrice: number }[];
  }) => {
    const subtotal = payload.lineItems.reduce((s, item) => s + item.quantity * item.unitPrice, 0);
    const vatRate = 20;
    const vatAmount = Math.round(subtotal * (vatRate / 100));
    const total = subtotal + vatAmount;
    createInvoice.mutate(
      {
        ...payload,
        status: 'draft',
        jobId: null,
        quoteId: null,
        lineItems: payload.lineItems.map((item, i) => ({ id: `li-${Date.now()}-${i}`, ...item, total: item.quantity * item.unitPrice })),
        subtotal,
        vatRate,
        vatAmount,
        total,
        amountPaid: 0,
        amountDue: total,
        paidAt: null,
        paymentMethod: null,
      },
      {
        onSuccess: () => {
          toast.success('Invoice created');
          setIsDialogOpen(false);
        },
        onError: (err) => toast.error(err.message || 'Failed to create invoice'),
      }
    );
  };

  const handleSend = (id: string) => {
    sendInvoice.mutate(id, {
      onSuccess: () => toast.success('Invoice sent'),
      onError: (err) => toast.error(err.message || 'Failed to send invoice'),
    });
  };

  if (isLoading && !invoices) return <div className="bg-white rounded-xl h-96 animate-pulse" />;
  if (error) return <div className="text-center py-12 text-[#DC2626]">Failed to load invoices</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-xl font-semibold text-[#1C1917]">Invoices</h2>
          <span className="px-2 py-0.5 bg-[#F5F4F0] rounded-full text-xs font-medium text-[#57534E]">{filtered.length}</span>
        </div>
        <button
          onClick={() => setIsDialogOpen(true)}
          className="h-9 px-4 flex items-center gap-2 rounded-lg bg-[#D4650A] text-white text-xs font-semibold hover:bg-[#B85500] transition-colors"
        >
          <Plus className="w-4 h-4" /> Create Invoice
        </button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white rounded-xl border border-[#E7E5E4] p-4 shadow-sm">
          <div className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[#78716C] mb-1">Total Paid</div>
          <div className="text-xl font-bold text-[#16A34A]">{formatGBP(totalPaid)}</div>
        </div>
        <div className="bg-white rounded-xl border border-[#E7E5E4] p-4 shadow-sm">
          <div className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[#78716C] mb-1">Outstanding</div>
          <div className="text-xl font-bold text-[#D4650A]">{formatGBP(totalOutstanding)}</div>
        </div>
        <div className={`rounded-xl border p-4 shadow-sm ${overdueCount > 0 ? 'bg-[#FEF2F2] border-[#FECACA]' : 'bg-white border-[#E7E5E4]'}`}>
          <div className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[#78716C] mb-1">Overdue</div>
          <div className={`text-xl font-bold ${overdueCount > 0 ? 'text-[#DC2626]' : 'text-[#1C1917]'}`}>
            {overdueCount > 0 && <AlertTriangle className="w-5 h-5 inline mr-1" />}
            {overdueCount} invoice{overdueCount !== 1 ? 's' : ''}
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl border border-[#E7E5E4] p-3 flex items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#A8A29E]" />
          <input type="text" placeholder="Search invoices..." value={search} onChange={e => setSearch(e.target.value)}
            className="w-full h-9 pl-9 pr-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
        </div>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="h-9 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A] bg-white">
          <option value="all">All Status</option>
          <option value="draft">Draft</option>
          <option value="sent">Sent</option>
          <option value="viewed">Viewed</option>
          <option value="paid">Paid</option>
          <option value="overdue">Overdue</option>
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
                <th className="text-left px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.05em] text-[#78716C]">Issue Date</th>
                <th className="text-left px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.05em] text-[#78716C]">Due Date</th>
                <th className="text-right px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.05em] text-[#78716C]">Amount</th>
                <th className="text-left px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.05em] text-[#78716C]">Status</th>
                <th className="text-center px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.05em] text-[#78716C]">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(inv => (
                <tr key={inv.id} className="border-t border-[#F0EFEA] hover:bg-[#F5F4F0] transition-colors cursor-pointer">
                  <td className="px-4 py-3">
                    <Link to={`/invoices/${inv.id}`} className="font-mono text-sm text-[#1C1917] hover:text-[#D4650A]">{inv.reference}</Link>
                  </td>
                  <td className="px-4 py-3 text-sm text-[#1C1917]">{inv.customer.firstName} {inv.customer.lastName}</td>
                  <td className="px-4 py-3 text-xs text-[#78716C]">{new Date(inv.issueDate).toLocaleDateString('en-GB')}</td>
                  <td className="px-4 py-3 text-xs text-[#78716C]">{new Date(inv.dueDate).toLocaleDateString('en-GB')}</td>
                  <td className="px-4 py-3 text-sm font-semibold text-[#1C1917] text-right">{formatGBP(inv.total)}</td>
                  <td className="px-4 py-3"><StatusPill status={inv.status} /></td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-center">
                      {inv.status === 'draft' && (
                        <button onClick={() => handleSend(inv.id)} title="Send" className="p-1.5 hover:bg-[#EFF6FF] rounded text-[#2563EB]"><Send className="w-3.5 h-3.5" /></button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {filtered.length === 0 && <div className="py-12 text-center text-sm text-[#A8A29E]">No invoices found</div>}
      </div>

      {isDialogOpen && <InvoiceDialog contacts={contacts ?? []} onClose={() => setIsDialogOpen(false)} onSubmit={handleCreate} isSubmitting={createInvoice.isPending} />}
    </div>
  );
}

function InvoiceDialog({
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
    issueDate: string;
    dueDate: string;
    lineItems: { description: string; quantity: number; unit: string; unitPrice: number }[];
  }) => void;
  isSubmitting: boolean;
}) {
  const [customerId, setCustomerId] = useState('');
  const [reference, setReference] = useState('');
  const [issueDate, setIssueDate] = useState(new Date().toISOString().split('T')[0]);
  const [dueDate, setDueDate] = useState(new Date().toISOString().split('T')[0]);
  const [description, setDescription] = useState('');
  const [quantity, setQuantity] = useState(1);
  const [unit, setUnit] = useState('item');
  const [unitPrice, setUnitPrice] = useState(0);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-md p-6 space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-[#1C1917]">New Invoice</h3>
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
          <div className="grid grid-cols-2 gap-3">
            <input type="date" value={issueDate} onChange={e => setIssueDate(e.target.value)} className="h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
            <input type="date" value={dueDate} onChange={e => setDueDate(e.target.value)} className="h-10 px-3 text-sm border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#D4650A]" />
          </div>
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
            disabled={isSubmitting || !customerId || !reference}
            onClick={() => onSubmit({ customerId, reference, issueDate, dueDate, lineItems: [{ description, quantity, unit, unitPrice }] })}
            className="h-9 px-4 text-sm font-semibold bg-[#D4650A] text-white rounded-lg hover:bg-[#B85500] disabled:opacity-50"
          >
            {isSubmitting ? 'Saving...' : 'Create Invoice'}
          </button>
        </div>
      </div>
    </div>
  );
}
