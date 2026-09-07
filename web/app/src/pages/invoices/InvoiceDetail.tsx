import { useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Send, CheckCircle, FileDown, XCircle } from 'lucide-react';
import { useInvoice, useSendInvoice, useMarkInvoicePaid, useCancelInvoice, useSettings } from '@/lib/api/hooks';
import { useUiStore } from '@/stores/uiStore';
import { StatusPill } from '@/components/shared/StatusPill';
import { formatGBP } from '@/lib/utils';
import { toast } from 'sonner';

export function InvoiceDetail() {
  const { id = '' } = useParams<{ id: string }>();
  const setPageTitle = useUiStore(s => s.setPageTitle);
  const { data: invoice, isLoading, error } = useInvoice(id);
  const { data: tenant } = useSettings();
  const sendInvoice = useSendInvoice();
  const markPaid = useMarkInvoicePaid();
  const cancelInvoice = useCancelInvoice();

  useEffect(() => {
    setPageTitle('Invoice Detail');
  }, [setPageTitle]);

  if (isLoading) return <div className="animate-pulse bg-white rounded-xl h-96" />;
  if (error || !invoice) return <div className="text-center py-12 text-[#A8A29E]">Invoice not found</div>;

  const handleSend = () => {
    sendInvoice.mutate(invoice.id, {
      onSuccess: () => toast.success('Invoice sent'),
      onError: (err) => toast.error(err.message || 'Failed to send invoice'),
    });
  };

  const handleMarkPaid = () => {
    markPaid.mutate({ id: invoice.id, paymentMethod: 'bank_transfer' }, {
      onSuccess: () => toast.success('Invoice marked as paid'),
      onError: (err) => toast.error(err.message || 'Failed to mark invoice paid'),
    });
  };

  const handleCancel = () => {
    if (!confirm('Cancel this invoice?')) return;
    cancelInvoice.mutate(invoice.id, {
      onSuccess: () => toast.success('Invoice cancelled'),
      onError: (err) => toast.error(err.message || 'Failed to cancel invoice'),
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm">
        <Link to="/invoices" className="text-[#78716C] hover:text-[#D4650A]">Invoices</Link>
        <span className="text-[#A8A29E]">/</span>
        <span className="font-mono text-[#1C1917]">{invoice.reference}</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <div className="bg-white rounded-xl border border-[#E7E5E4] p-8 shadow-sm">
            <div className="flex justify-between items-start mb-6">
              <div>
                <div className="text-xl font-bold text-[#1C1917]">{tenant?.name ?? 'Your Business'}</div>
                {tenant?.address && <div className="text-sm text-[#57534E]">{tenant.address}</div>}
                {(tenant?.phone || tenant?.email) && (
                  <div className="text-sm text-[#57534E]">
                    {tenant?.phone}{tenant?.phone && tenant?.email ? ' · ' : ''}{tenant?.email}
                  </div>
                )}
              </div>
              <div className="text-right">
                <div className="font-mono text-2xl font-bold text-[#1C1917]">{invoice.reference}</div>
                <StatusPill status={invoice.status} />
              </div>
            </div>

            <div className="border-t border-b border-[#F0EFEA] py-4 mb-6">
              <div className="text-sm font-semibold text-[#78716C] uppercase tracking-[0.05em] mb-2">Bill To</div>
              <div className="text-sm font-semibold text-[#1C1917]">{invoice.customer.firstName} {invoice.customer.lastName}</div>
              {invoice.customer.address && <div className="text-sm text-[#57534E]">{invoice.customer.address}</div>}
              <div className="text-sm text-[#57534E]">{invoice.customer.email}</div>
            </div>

            <table className="w-full mb-6">
              <thead>
                <tr className="border-b border-[#F0EFEA]">
                  <th className="text-left py-2 text-[11px] font-semibold uppercase text-[#78716C]">Description</th>
                  <th className="text-right py-2 text-[11px] font-semibold uppercase text-[#78716C]">Qty</th>
                  <th className="text-right py-2 text-[11px] font-semibold uppercase text-[#78716C]">Unit Price</th>
                  <th className="text-right py-2 text-[11px] font-semibold uppercase text-[#78716C]">Total</th>
                </tr>
              </thead>
              <tbody>
                {invoice.lineItems.map(item => (
                  <tr key={item.id} className="border-b border-[#F0EFEA]">
                    <td className="py-2.5 text-sm text-[#1C1917]">{item.description}</td>
                    <td className="py-2.5 text-sm text-[#57534E] text-right">{item.quantity} {item.unit}</td>
                    <td className="py-2.5 text-sm text-[#57534E] text-right">{formatGBP(item.unitPrice)}</td>
                    <td className="py-2.5 text-sm font-medium text-[#1C1917] text-right">{formatGBP(item.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="space-y-1 max-w-xs ml-auto">
              <div className="flex justify-between text-sm text-[#57534E]"><span>Subtotal</span><span>{formatGBP(invoice.subtotal)}</span></div>
              <div className="flex justify-between text-sm text-[#57534E]"><span>VAT ({Math.round(invoice.vatRate * 100)}%)</span><span>{formatGBP(invoice.vatAmount)}</span></div>
              <div className="flex justify-between text-lg font-bold text-[#1C1917] pt-2 border-t border-[#F0EFEA]"><span>Total</span><span>{formatGBP(invoice.total)}</span></div>
              {invoice.amountPaid > 0 && <div className="flex justify-between text-sm text-[#16A34A]"><span>Paid</span><span>{formatGBP(invoice.amountPaid)}</span></div>}
              {invoice.amountDue > 0 && <div className="flex justify-between text-sm text-[#DC2626] font-semibold"><span>Amount Due</span><span>{formatGBP(invoice.amountDue)}</span></div>}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-[#1C1917] mb-3 uppercase tracking-[0.05em]">Actions</h3>
            <div className="space-y-2">
              {invoice.status !== 'paid' && invoice.status !== 'cancelled' && (
                <button onClick={handleSend} disabled={sendInvoice.isPending} className="w-full h-10 flex items-center justify-center gap-2 rounded-lg bg-[#D4650A] text-white text-xs font-semibold hover:bg-[#B85500] transition-colors disabled:opacity-50">
                  <Send className="w-4 h-4" /> Send Reminder
                </button>
              )}
              {invoice.status !== 'paid' && invoice.status !== 'cancelled' && (
                <button onClick={handleMarkPaid} disabled={markPaid.isPending} className="w-full h-10 flex items-center justify-center gap-2 rounded-lg bg-[#F5F4F0] border border-[#E7E5E4] text-[#1C1917] text-xs font-semibold hover:bg-[#EFEEE9] transition-colors disabled:opacity-50">
                  <CheckCircle className="w-4 h-4" /> Mark as Paid
                </button>
              )}
              {invoice.status !== 'paid' && invoice.status !== 'cancelled' && (
                <button onClick={handleCancel} disabled={cancelInvoice.isPending} className="w-full h-10 flex items-center justify-center gap-2 rounded-lg text-[#DC2626] text-xs font-medium hover:bg-[#FEF2F2] transition-colors disabled:opacity-50">
                  <XCircle className="w-4 h-4" /> Cancel Invoice
                </button>
              )}
              <button className="w-full h-10 flex items-center justify-center gap-2 rounded-lg text-[#57534E] text-xs font-medium hover:bg-[#F5F4F0] transition-colors">
                <FileDown className="w-4 h-4" /> Download PDF
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
