import { useEffect, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { Sparkles, Send, Edit, FileDown, Wrench, CheckCircle, XCircle, Trash2, TriangleAlert } from 'lucide-react';
import { API_BASE_URL } from '@/lib/api/client';
import { useQuote, useSendQuote, useApproveQuote, useRejectQuote, useConvertQuoteToInvoice, useDeleteQuote, useUpdateQuote, useRefineQuote } from '@/lib/api/hooks';
import { useUiStore } from '@/stores/uiStore';
import { StatusPill } from '@/components/shared/StatusPill';
import { toast } from 'sonner';

function formatCurrency(value: number, fractionDigits = 2): string {
  return value.toLocaleString('en-GB', {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  });
}

export function QuoteDetail() {
  const { id = '' } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const setPageTitle = useUiStore(s => s.setPageTitle);
  const { data: quote, isLoading, error } = useQuote(id);
  const sendQuote = useSendQuote();
  const updateQuote = useUpdateQuote();
  const refineQuote = useRefineQuote();
  const approveQuote = useApproveQuote();
  const rejectQuote = useRejectQuote();
  const convertQuote = useConvertQuoteToInvoice();
  const deleteQuote = useDeleteQuote();
  const [isEditing, setIsEditing] = useState(false);
  const [draftItems, setDraftItems] = useState<Array<{ id: string; description: string; quantity: number; unitPrice: number }>>([]);
  const [refineInstructions, setRefineInstructions] = useState('');

  useEffect(() => {
    setPageTitle('Quote Detail');
  }, [setPageTitle]);

  useEffect(() => {
    if (!quote) return;
    setDraftItems(
      quote.lineItems.map((item) => ({
        id: item.id,
        description: item.description,
        quantity: item.quantity,
        unitPrice: item.unitPrice,
      })),
    );
  }, [quote]);

  if (isLoading) return <div className="animate-pulse bg-white rounded-xl h-96" />;
  if (error || !quote) return <div className="text-center py-12 text-[#A8A29E]">Quote not found</div>;

  const vatRateMultiplier = quote.vatRate > 1 ? quote.vatRate / 100 : quote.vatRate;
  const vatRateDisplay = vatRateMultiplier * 100;
  const editingSubtotal = draftItems.reduce((sum, item) => sum + (item.quantity * item.unitPrice), 0);
  const editingVat = editingSubtotal * vatRateMultiplier;
  const editingTotal = editingSubtotal + editingVat;
  const aiGeneratedLineIds = new Set(quote.lineItems.filter((item) => item.aiGenerated).map((item) => item.id));

  const handleSend = () => {
    sendQuote.mutate(quote.id, {
      onSuccess: () => toast.success('Quote sent'),
      onError: (err) => toast.error(err.message || 'Failed to send quote'),
    });
  };

  const handleApprove = () => {
    approveQuote.mutate(quote.id, {
      onSuccess: () => toast.success('Quote approved'),
      onError: (err) => toast.error(err.message || 'Failed to approve quote'),
    });
  };

  const handleReject = () => {
    rejectQuote.mutate(quote.id, {
      onSuccess: () => toast.success('Quote rejected'),
      onError: (err) => toast.error(err.message || 'Failed to reject quote'),
    });
  };

  const handleConvert = () => {
    convertQuote.mutate(quote.id, {
      onSuccess: (invoice) => {
        toast.success('Quote converted to invoice');
        if (invoice?.id) navigate(`/invoices/${invoice.id}`);
      },
      onError: (err) => toast.error(err.message || 'Failed to convert quote'),
    });
  };

  const handleDelete = () => {
    if (!confirm('Delete this quote?')) return;
    deleteQuote.mutate(quote.id, {
      onSuccess: () => {
        toast.success('Quote deleted');
        navigate('/quotes');
      },
      onError: (err) => toast.error(err.message || 'Failed to delete quote'),
    });
  };

  const handleStartEdit = () => {
    setIsEditing(true);
  };

  const handleCancelEdit = () => {
    setDraftItems(
      quote.lineItems.map((item) => ({
        id: item.id,
        description: item.description,
        quantity: item.quantity,
        unitPrice: item.unitPrice,
      })),
    );
    setIsEditing(false);
  };

  const handleDraftChange = (
    id: string,
    key: 'description' | 'quantity' | 'unitPrice',
    value: string,
  ) => {
    setDraftItems((current) =>
      current.map((item) => {
        if (item.id !== id) return item;
        if (key === 'description') {
          return { ...item, description: value };
        }
        const numeric = Number(value);
        if (Number.isNaN(numeric)) return item;
        return { ...item, [key]: numeric };
      }),
    );
  };

  const handleAddLineItem = () => {
    setDraftItems((current) => [
      ...current,
      {
        id: `new-${crypto.randomUUID()}`,
        description: 'New line item',
        quantity: 1,
        unitPrice: 0,
      },
    ]);
  };

  const handleRemoveLineItem = (id: string) => {
    setDraftItems((current) => current.filter((item) => item.id !== id));
  };

  const handleSaveEdit = () => {
    const sanitized = draftItems
      .map((item) => ({
        description: item.description.trim(),
        quantity: Math.max(0, item.quantity),
        unitPrice: Math.max(0, item.unitPrice),
      }))
      .filter((item) => item.description.length > 0);

    if (sanitized.length === 0) {
      toast.error('At least one line item is required');
      return;
    }

    updateQuote.mutate(
      {
        id: quote.id,
        data: {
          lineItems: sanitized.map((item) => ({
            id: '',
            description: item.description,
            quantity: item.quantity,
            unit: 'item',
            unitPrice: item.unitPrice,
            total: item.quantity * item.unitPrice,
            aiGenerated: false,
            isAiSuggested: false,
          })),
        },
      },
      {
        onSuccess: () => {
          toast.success('Quote updated');
          setIsEditing(false);
        },
        onError: (err) => toast.error(err.message || 'Failed to update quote'),
      },
    );
  };

  const handleDownloadPdf = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/quotes/${quote.id}/pdf`, {
        credentials: 'include',
      });
      if (!response.ok) throw new Error('Failed to generate PDF');
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `quote-${quote.id}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success('PDF downloaded');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to download PDF');
    }
  };

  const handleRefine = () => {
    const instructions = refineInstructions.trim();
    if (!instructions) return;
    refineQuote.mutate(
      { id: quote.id, instructions },
      {
        onSuccess: () => {
          toast.success('Quote refined');
          setRefineInstructions('');
        },
        onError: (err) => toast.error(err.message || 'Failed to refine quote'),
      },
    );
  };

  return (
    <div className="space-y-4">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm">
        <Link to="/quotes" className="text-[#78716C] hover:text-[#D4650A] transition-colors">Quotes</Link>
        <span className="text-[#A8A29E]">/</span>
        <span className="font-mono text-[#1C1917]">{quote.reference}</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Left column */}
        <div className="lg:col-span-2 space-y-4">
          {/* Quote header */}
          <div className="bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm">
            <div className="flex items-start justify-between mb-4">
              <div>
                <div className="font-mono text-lg font-semibold text-[#1C1917]">{quote.reference}</div>
                <StatusPill status={quote.status} />
              </div>
              <div className="text-right">
                <div className="text-2xl font-bold text-[#1C1917]">£{formatCurrency(quote.total)}</div>
                <div className="text-xs text-[#78716C]">inc. VAT</div>
              </div>
            </div>
            <div className="flex items-center gap-3 pt-4 border-t border-[#F0EFEA]">
              {quote.customer.avatarUrl ? (
                <img src={quote.customer.avatarUrl} alt="" className="w-10 h-10 rounded-full object-cover" />
              ) : (
                <div className="w-10 h-10 rounded-full bg-[#F5F4F0] flex items-center justify-center text-sm font-semibold text-[#57534E]">
                  {quote.customer.firstName[0]}{quote.customer.lastName[0]}
                </div>
              )}
              <div>
                <div className="text-sm font-semibold text-[#1C1917]">{quote.customer.firstName} {quote.customer.lastName}</div>
                <div className="text-xs text-[#78716C]">{quote.customer.email} · {quote.customer.phone}</div>
              </div>
            </div>
            <div className="mt-3 text-sm text-[#57534E]">{quote.serviceType}</div>
            <div className="text-xs text-[#78716C]">{quote.propertyAddress}</div>
          </div>

          {/* Line items */}
          <div className="bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm">
            <div className="mb-3 flex items-center justify-between gap-3">
              <h3 className="text-sm font-semibold text-[#1C1917] uppercase tracking-[0.05em]">Quote Items</h3>
              {isEditing ? (
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleSaveEdit}
                    disabled={updateQuote.isPending}
                    className="h-8 rounded-md bg-[#D4650A] px-3 text-xs font-semibold uppercase tracking-[0.05em] text-white hover:bg-[#B85500] disabled:opacity-50"
                  >
                    Save
                  </button>
                  <button
                    onClick={handleCancelEdit}
                    className="h-8 rounded-md border border-[#E7E5E4] bg-white px-3 text-xs font-semibold uppercase tracking-[0.05em] text-[#57534E] hover:bg-[#F5F4F0]"
                  >
                    Cancel
                  </button>
                </div>
              ) : null}
            </div>
            <table className="w-full">
              <thead>
                <tr className="border-b border-[#F0EFEA]">
                  <th className="text-left py-2 text-[11px] font-semibold uppercase text-[#78716C]">Item</th>
                  <th className="text-right py-2 text-[11px] font-semibold uppercase text-[#78716C]">Qty</th>
                  <th className="text-right py-2 text-[11px] font-semibold uppercase text-[#78716C]">Unit Price</th>
                  <th className="text-right py-2 text-[11px] font-semibold uppercase text-[#78716C]">Total</th>
                </tr>
              </thead>
              <tbody>
                {(isEditing ? draftItems : quote.lineItems).map(item => (
                  <tr key={item.id} className="border-b border-[#F0EFEA] last:border-0">
                    <td className="py-2.5 text-sm text-[#1C1917]">
                      {isEditing ? (
                        <input
                          value={item.description}
                          onChange={(e) => handleDraftChange(item.id, 'description', e.target.value)}
                          className="w-full rounded-md border border-[#E7E5E4] px-2 py-1 text-sm"
                        />
                      ) : (
                        <span className="flex items-center gap-1.5">
                          {item.description}
                          {aiGeneratedLineIds.has(item.id) && (
                            <span title="AI suggested" className="inline-flex">
                              <Sparkles
                                className="w-3.5 h-3.5 text-[#7C3AED] flex-shrink-0"
                                aria-label="AI suggested line"
                              />
                            </span>
                          )}
                        </span>
                      )}
                    </td>
                    <td className="py-2.5 text-sm text-[#57534E] text-right">
                      {isEditing ? (
                        <input
                          type="number"
                          min={0}
                          step="0.1"
                          value={item.quantity}
                          onChange={(e) => handleDraftChange(item.id, 'quantity', e.target.value)}
                          className="w-20 rounded-md border border-[#E7E5E4] px-2 py-1 text-right text-sm"
                        />
                      ) : <>{item.quantity} item</>}
                    </td>
                    <td className="py-2.5 text-sm text-[#57534E] text-right">
                      {isEditing ? (
                        <input
                          type="number"
                          min={0}
                          step="0.01"
                          value={item.unitPrice}
                          onChange={(e) => handleDraftChange(item.id, 'unitPrice', e.target.value)}
                          className="w-28 rounded-md border border-[#E7E5E4] px-2 py-1 text-right text-sm"
                        />
                      ) : <>£{formatCurrency(item.unitPrice)}</>}
                    </td>
                    <td className="py-2.5 text-sm font-medium text-[#1C1917] text-right">
                      £{formatCurrency(item.quantity * item.unitPrice)}
                    </td>
                    {isEditing ? (
                      <td className="py-2.5 pl-2 text-right">
                        <button
                          onClick={() => handleRemoveLineItem(item.id)}
                          className="text-xs font-medium text-[#DC2626] hover:underline"
                        >
                          Remove
                        </button>
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
            {isEditing ? (
              <div className="mt-3">
                <button
                  onClick={handleAddLineItem}
                  className="rounded-md border border-[#E7E5E4] bg-white px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.05em] text-[#57534E] hover:bg-[#F5F4F0]"
                >
                  Add Line Item
                </button>
              </div>
            ) : null}
            <div className="mt-4 pt-4 border-t border-[#F0EFEA] space-y-1">
              <div className="flex justify-between text-sm text-[#57534E]"><span>Subtotal</span><span>£{formatCurrency(isEditing ? editingSubtotal : quote.subtotal)}</span></div>
              <div className="flex justify-between text-sm text-[#57534E]"><span>VAT ({formatCurrency(vatRateDisplay, 0)}%)</span><span>£{formatCurrency(isEditing ? editingVat : quote.vatAmount)}</span></div>
              <div className="flex justify-between text-lg font-bold text-[#1C1917]"><span>Total</span><span>£{formatCurrency(isEditing ? editingTotal : quote.total)}</span></div>
            </div>
          </div>

          {/* AI Panel */}
          {quote.aiGenerated && (
            <div className="bg-[#F5F3FF] rounded-xl border border-[#EDE9FE] p-5">
              <div className="flex items-center gap-2 mb-1">
                <Sparkles className="w-4 h-4 text-[#7C3AED]" />
                <span className="text-sm font-semibold text-[#7C3AED]">AI Generated</span>
              </div>
              <p className="text-xs text-[#78716C] mb-3">
                Guide prices generated by AI — review before sending.
              </p>
              {(quote.retrievalStatus === 'no_index' || quote.retrievalStatus === 'skipped_no_key') && (
                <div className="mb-3 text-xs text-[#78716C]">
                  Priced from AI knowledge (no catalogue match)
                </div>
              )}
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <span className="text-[#78716C]">Confidence: </span>
                  <span className="font-semibold text-[#1C1917]">
                    {quote.aiConfidence != null ? `${Math.round(quote.aiConfidence * 100)}%` : '—'}
                  </span>
                </div>
                <div><span className="text-[#78716C]">Generated: </span><span className="font-semibold text-[#1C1917]">{new Date(quote.createdAt).toLocaleString('en-GB')}</span></div>
              </div>
              {quote.aiConfidence != null && (
                <div className="mt-3 h-2 bg-white rounded-full overflow-hidden">
                  <div className="h-full bg-[#7C3AED] rounded-full transition-all" style={{ width: `${Math.round(quote.aiConfidence * 100)}%` }} />
                </div>
              )}
              {quote.aiWarnings.length > 0 && (
                <div className="mt-3 p-3 bg-[#FFFBEB] border border-[#FDE68A] rounded-lg">
                  <div className="flex items-center gap-1.5 mb-1 text-xs font-semibold uppercase tracking-[0.05em] text-[#B45309]">
                    <TriangleAlert className="w-3.5 h-3.5" /> Warnings
                  </div>
                  <ul className="space-y-1 text-xs text-[#92400E]">
                    {quote.aiWarnings.map((warning) => (
                      <li key={warning}>• {warning}</li>
                    ))}
                  </ul>
                </div>
              )}
              {quote.aiAssumptions.length > 0 && (
                <div className="mt-3 p-3 bg-white/60 border border-[#EDE9FE] rounded-lg">
                  <div className="mb-1 text-xs font-semibold uppercase tracking-[0.05em] text-[#78716C]">
                    Assumptions
                  </div>
                  <ul className="space-y-1 text-xs text-[#57534E]">
                    {quote.aiAssumptions.map((assumption) => (
                      <li key={assumption}>• {assumption}</li>
                    ))}
                  </ul>
                </div>
              )}
              {quote.aiNotes && (
                <p className="mt-3 text-xs text-[#57534E]">{quote.aiNotes}</p>
              )}

              {/* Refine with AI */}
              <div className="mt-4 pt-4 border-t border-[#EDE9FE]">
                <label htmlFor="refine-instructions" className="block text-[11px] font-semibold uppercase tracking-[0.05em] text-[#78716C] mb-1">
                  Refine with AI
                </label>
                <textarea
                  id="refine-instructions"
                  value={refineInstructions}
                  onChange={(e) => setRefineInstructions(e.target.value)}
                  placeholder="e.g. Add 2 more double sockets in the kitchen"
                  rows={2}
                  className="w-full p-2 text-sm bg-white border border-[#E7E5E4] rounded-lg focus:outline-none focus:border-[#7C3AED] resize-none"
                />
                <button
                  onClick={handleRefine}
                  disabled={refineQuote.isPending || !refineInstructions.trim()}
                  className="mt-2 h-8 px-3 flex items-center gap-2 rounded-md bg-[#7C3AED] text-white text-xs font-semibold uppercase tracking-[0.05em] hover:bg-[#6D28D9] transition-colors disabled:opacity-50"
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  {refineQuote.isPending ? 'Refining...' : 'Refine quote'}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Right column - Actions */}
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-[#1C1917] mb-3 uppercase tracking-[0.05em]">Actions</h3>
            <div className="space-y-2">
              {quote.status === 'draft' && (
                <button onClick={handleSend} disabled={sendQuote.isPending} className="w-full h-10 flex items-center justify-center gap-2 rounded-lg bg-[#D4650A] text-white text-xs font-semibold uppercase tracking-[0.05em] hover:bg-[#B85500] transition-colors disabled:opacity-50">
                  <Send className="w-4 h-4" /> Send to Customer
                </button>
              )}
              {quote.status === 'sent' && (
                <button onClick={handleApprove} disabled={approveQuote.isPending} className="w-full h-10 flex items-center justify-center gap-2 rounded-lg bg-[#16A34A] text-white text-xs font-semibold uppercase tracking-[0.05em] hover:bg-[#15803D] transition-colors disabled:opacity-50">
                  <CheckCircle className="w-4 h-4" /> Approve Quote
                </button>
              )}
              {(quote.status === 'draft' || quote.status === 'sent') && (
                <button onClick={handleReject} disabled={rejectQuote.isPending} className="w-full h-10 flex items-center justify-center gap-2 rounded-lg bg-[#F5F4F0] border border-[#E7E5E4] text-[#1C1917] text-xs font-semibold uppercase tracking-[0.05em] hover:bg-[#EFEEE9] transition-colors disabled:opacity-50">
                  <XCircle className="w-4 h-4" /> Reject Quote
                </button>
              )}
              {quote.status === 'accepted' && (
                <button onClick={handleConvert} disabled={convertQuote.isPending} className="w-full h-10 flex items-center justify-center gap-2 rounded-lg bg-[#F5F4F0] border border-[#E7E5E4] text-[#1C1917] text-xs font-semibold uppercase tracking-[0.05em] hover:bg-[#EFEEE9] transition-colors disabled:opacity-50">
                  <Wrench className="w-4 h-4" /> Convert to Invoice
                </button>
              )}
              <button onClick={isEditing ? handleCancelEdit : handleStartEdit} className="w-full h-10 flex items-center justify-center gap-2 rounded-lg bg-[#F5F4F0] border border-[#E7E5E4] text-[#1C1917] text-xs font-semibold uppercase tracking-[0.05em] hover:bg-[#EFEEE9] transition-colors">
                <Edit className="w-4 h-4" /> {isEditing ? 'Cancel Edit' : 'Edit Quote'}
              </button>
              <button onClick={handleDownloadPdf} className="w-full h-10 flex items-center justify-center gap-2 rounded-lg text-[#57534E] text-xs font-medium hover:bg-[#F5F4F0] transition-colors">
                <FileDown className="w-4 h-4" /> Download PDF
              </button>
              <button onClick={handleDelete} disabled={deleteQuote.isPending} className="w-full h-10 flex items-center justify-center gap-2 rounded-lg text-[#DC2626] text-xs font-medium hover:bg-[#FEF2F2] transition-colors disabled:opacity-50">
                <Trash2 className="w-4 h-4" /> Delete Quote
              </button>
            </div>
          </div>

          {/* Timeline */}
          <div className="bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-[#1C1917] mb-3 uppercase tracking-[0.05em]">Quote History</h3>
            <div className="space-y-4">
              {quote.acceptedAt && (
                <div className="flex gap-3">
                  <div className="w-2.5 h-2.5 rounded-full bg-[#16A34A] mt-1.5 flex-shrink-0" />
                  <div>
                    <div className="text-sm text-[#1C1917]">Quote accepted by {quote.customer.firstName} {quote.customer.lastName}</div>
                    <div className="text-[11px] text-[#78716C]">{new Date(quote.acceptedAt).toLocaleString('en-GB')}</div>
                  </div>
                </div>
              )}
              {quote.sentAt && (
                <div className="flex gap-3">
                  <div className="w-2.5 h-2.5 rounded-full bg-[#2563EB] mt-1.5 flex-shrink-0" />
                  <div>
                    <div className="text-sm text-[#1C1917]">Quote sent via email</div>
                    <div className="text-[11px] text-[#78716C]">{new Date(quote.sentAt).toLocaleString('en-GB')}</div>
                  </div>
                </div>
              )}
              {quote.aiGenerated && (
                <div className="flex gap-3">
                  <div className="w-2.5 h-2.5 rounded-full bg-[#7C3AED] mt-1.5 flex-shrink-0" />
                  <div>
                    <div className="text-sm text-[#1C1917]">AI generated quote</div>
                    <div className="text-[11px] text-[#78716C]">{new Date(quote.createdAt).toLocaleString('en-GB')}</div>
                  </div>
                </div>
              )}
              <div className="flex gap-3">
                <div className="w-2.5 h-2.5 rounded-full bg-[#D4650A] mt-1.5 flex-shrink-0" />
                <div>
                  <div className="text-sm text-[#1C1917]">Quote request received</div>
                  <div className="text-[11px] text-[#78716C]">{new Date(quote.createdAt).toLocaleString('en-GB')}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
