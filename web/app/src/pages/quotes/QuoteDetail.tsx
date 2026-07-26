import { useEffect, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { Sparkles, Send, Edit, FileDown, Wrench, CheckCircle, XCircle, Trash2 } from 'lucide-react';
import { API_BASE_URL } from '@/lib/api/client';
import { useQuote, useSendQuote, useApproveQuote, useRejectQuote, useConvertQuoteToInvoice, useDeleteQuote, useQuoteBoq, useUpdateQuote, useUpdateQuoteBoq } from '@/lib/api/hooks';
import { useUiStore } from '@/stores/uiStore';
import { StatusPill } from '@/components/shared/StatusPill';
import { toast } from 'sonner';

function formatCurrency(value: number, fractionDigits = 2): string {
  return value.toLocaleString('en-GB', {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  });
}

function formatCurrencySafe(value: number, fractionDigits = 2): string {
  if (!Number.isFinite(value)) return formatCurrency(0, fractionDigits);
  return formatCurrency(value, fractionDigits);
}

export function QuoteDetail() {
  const { id = '' } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const setPageTitle = useUiStore(s => s.setPageTitle);
  const { data: quote, isLoading, error } = useQuote(id);
  const { data: boq } = useQuoteBoq(id);
  const sendQuote = useSendQuote();
  const updateQuote = useUpdateQuote();
  const updateQuoteBoq = useUpdateQuoteBoq();
  const approveQuote = useApproveQuote();
  const rejectQuote = useRejectQuote();
  const convertQuote = useConvertQuoteToInvoice();
  const deleteQuote = useDeleteQuote();
  const [isEditing, setIsEditing] = useState(false);
  const [draftItems, setDraftItems] = useState<Array<{ id: string; description: string; quantity: number; unitPrice: number }>>([]);
  const [isBoqEditing, setIsBoqEditing] = useState(false);
  const [draftBoqItems, setDraftBoqItems] = useState<Array<{
    id: string;
    code: string;
    description: string;
    category: string | null;
    unit: string;
    quantity: number;
    labourHours: number;
    labourRate: number;
    labourTotal: number;
    materialCost: number;
    materialTotal: number;
    plantCost: number;
    plantTotal: number;
    supplier: string | null;
    brand: string | null;
    sku: string | null;
    productUrl: string | null;
    retailPriceInclVat: number | null;
    notes: string | null;
  }>>([]);

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

  useEffect(() => {
    if (!boq) return;
    setDraftBoqItems(
      boq.lineItems.map((item) => ({
        id: item.id,
        code: item.code,
        description: item.description,
        category: item.category,
        unit: item.unit,
        quantity: item.quantity,
        labourHours: item.labourHours,
        labourRate: item.labourRate,
        labourTotal: item.labourTotal,
        materialCost: item.materialCost,
        materialTotal: item.materialTotal,
        plantCost: item.plantCost,
        plantTotal: item.plantTotal,
        supplier: item.supplier,
        brand: item.brand,
        sku: item.sku,
        productUrl: item.productUrl,
        retailPriceInclVat: item.retailPriceInclVat,
        notes: item.notes,
      })),
    );
  }, [boq]);

  if (isLoading) return <div className="animate-pulse bg-white rounded-xl h-96" />;
  if (error || !quote) return <div className="text-center py-12 text-[#A8A29E]">Quote not found</div>;

  const vatRateMultiplier = quote.vatRate > 1 ? quote.vatRate / 100 : quote.vatRate;
  const vatRateDisplay = vatRateMultiplier * 100;
  const editingSubtotal = draftItems.reduce((sum, item) => sum + (item.quantity * item.unitPrice), 0);
  const editingVat = editingSubtotal * vatRateMultiplier;
  const editingTotal = editingSubtotal + editingVat;

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

  const handleBoqDraftChange = (
    id: string,
    key: 'description' | 'quantity' | 'labourTotal' | 'materialTotal' | 'plantTotal' | 'notes',
    value: string,
  ) => {
    setDraftBoqItems((current) =>
      current.map((item) => {
        if (item.id !== id) return item;
        if (key === 'description') return { ...item, description: value };
        if (key === 'notes') return { ...item, notes: value };
        const numeric = Number(value);
        if (Number.isNaN(numeric)) return item;
        return { ...item, [key]: numeric };
      }),
    );
  };

  const handleBoqCancelEdit = () => {
    if (!boq) return;
    setDraftBoqItems(
      boq.lineItems.map((item) => ({
        id: item.id,
        code: item.code,
        description: item.description,
        category: item.category,
        unit: item.unit,
        quantity: item.quantity,
        labourHours: item.labourHours,
        labourRate: item.labourRate,
        labourTotal: item.labourTotal,
        materialCost: item.materialCost,
        materialTotal: item.materialTotal,
        plantCost: item.plantCost,
        plantTotal: item.plantTotal,
        supplier: item.supplier,
        brand: item.brand,
        sku: item.sku,
        productUrl: item.productUrl,
        retailPriceInclVat: item.retailPriceInclVat,
        notes: item.notes,
      })),
    );
    setIsBoqEditing(false);
  };

  const handleBoqSaveEdit = () => {
    if (!boq) return;
    const sanitized = draftBoqItems
      .map((item) => ({
        ...item,
        description: item.description.trim(),
        notes: item.notes?.trim() || null,
        quantity: Math.max(0, item.quantity),
        labourTotal: Math.max(0, item.labourTotal),
        materialTotal: Math.max(0, item.materialTotal),
        plantTotal: Math.max(0, item.plantTotal),
      }))
      .filter((item) => item.description.length > 0);

    if (sanitized.length === 0) {
      toast.error('At least one BoQ line item is required');
      return;
    }

    updateQuoteBoq.mutate(
      {
        quoteId: quote.id,
        data: {
          notes: boq.notes,
          lineItems: sanitized,
        },
      },
      {
        onSuccess: () => {
          toast.success('BoQ updated');
          setIsBoqEditing(false);
        },
        onError: (err) => toast.error(err.message || 'Failed to update BoQ'),
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
                      ) : item.description}
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

          {/* Bill of Quantities */}
          {boq && (
            <div className="bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-[#1C1917] uppercase tracking-[0.05em]">Bill of Quantities</h3>
                <div className="flex items-center gap-2">
                  <span className="text-xs px-2 py-1 rounded-full bg-[#F5F4F0] text-[#57534E]">{Math.round(boq.confidence * 100)}% confidence</span>
                  {isBoqEditing ? (
                    <>
                      <button
                        onClick={handleBoqSaveEdit}
                        disabled={updateQuoteBoq.isPending}
                        className="h-8 rounded-md bg-[#D4650A] px-3 text-xs font-semibold uppercase tracking-[0.05em] text-white hover:bg-[#B85500] disabled:opacity-50"
                      >
                        Save
                      </button>
                      <button
                        onClick={handleBoqCancelEdit}
                        className="h-8 rounded-md border border-[#E7E5E4] bg-white px-3 text-xs font-semibold uppercase tracking-[0.05em] text-[#57534E] hover:bg-[#F5F4F0]"
                      >
                        Cancel
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={() => setIsBoqEditing(true)}
                      className="h-8 rounded-md border border-[#E7E5E4] bg-white px-3 text-xs font-semibold uppercase tracking-[0.05em] text-[#57534E] hover:bg-[#F5F4F0]"
                    >
                      Edit BoQ
                    </button>
                  )}
                </div>
              </div>
              {boq.suppliers && boq.suppliers.length > 0 && (
                <div className="mb-3 text-xs text-[#78716C]">
                  Prices sourced from: {boq.suppliers.join(", ")}
                </div>
              )}
              <div className="mb-4 p-3 bg-[#FEF9C3] rounded-lg text-xs text-[#854D0E]">
                This is an indicative bill of quantities based on publicly listed supplier prices
                and rule-based/AI estimates. It is not a fixed quote. Supplier list prices (e.g.
                Screwfix/Toolstation) include VAT; the material costs below are shown excluding VAT
                and VAT is applied once to the quote total. Final pricing, availability, and
                specification must be confirmed with the named supplier(s) before contract.
              </div>

              {boq.customerSummaryLines.length > 0 && (
                <div className="mb-4 rounded-lg border border-[#E7E5E4] bg-[#FAFAF9] p-3">
                  <div className="mb-2 text-xs font-semibold uppercase tracking-[0.05em] text-[#57534E]">
                    Customer Quote View
                  </div>
                  <div className="space-y-1">
                    {boq.customerSummaryLines.map((line, idx) => (
                      <div key={`${line.description}-${idx}`} className="flex items-center justify-between text-sm">
                        <span className="text-[#1C1917]">{line.description}</span>
                        <span className="font-semibold text-[#1C1917]">£{formatCurrency(line.total)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {boq.marginIndicator && (
                <div className="mb-4 rounded-lg border border-[#E7E5E4] bg-white p-3">
                  <div className="mb-2 text-xs font-semibold uppercase tracking-[0.05em] text-[#57534E]">
                    Profit Margin Indicator
                  </div>
                  <div className="grid grid-cols-2 gap-y-1 text-xs">
                    <span className="text-[#78716C]">Materials</span>
                    <span className="text-right text-[#1C1917]">£{formatCurrency(boq.marginIndicator.materialSubtotal)}</span>
                    <span className="text-[#78716C]">Labour</span>
                    <span className="text-right text-[#1C1917]">£{formatCurrency(boq.marginIndicator.labourSubtotal)}</span>
                    <span className="text-[#78716C]">Target markup</span>
                    <span className="text-right text-[#1C1917]">{formatCurrency(boq.marginIndicator.targetMarkupPercent, 2)}%</span>
                    <span className="text-[#78716C]">Estimated margin</span>
                    <span className="text-right text-[#1C1917]">
                      £{formatCurrency(boq.marginIndicator.estimatedMarginAmount)} ({formatCurrency(boq.marginIndicator.estimatedMarginPercent, 2)}%)
                    </span>
                  </div>
                </div>
              )}

              <div className="overflow-x-auto">
              <table className="min-w-[980px] w-full">
                <thead>
                  <tr className="border-b border-[#F0EFEA]">
                    <th className="text-left py-2 text-[11px] font-semibold uppercase text-[#78716C]">Item</th>
                    <th className="text-right py-2 text-[11px] font-semibold uppercase text-[#78716C]">Qty</th>
                    <th className="text-right py-2 text-[11px] font-semibold uppercase text-[#78716C]">Labour</th>
                    <th className="text-right py-2 text-[11px] font-semibold uppercase text-[#78716C]">Materials</th>
                    <th className="text-right py-2 text-[11px] font-semibold uppercase text-[#78716C]">Plant</th>
                    <th className="text-right py-2 text-[11px] font-semibold uppercase text-[#78716C]">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {(isBoqEditing ? draftBoqItems : boq.lineItems).map(item => (
                    <tr key={item.id} className="border-b border-[#F0EFEA] last:border-0">
                      <td className="py-2.5 text-sm text-[#1C1917]">
                        <div>
                          {isBoqEditing ? (
                            <input
                              value={item.description}
                              onChange={(e) => handleBoqDraftChange(item.id, 'description', e.target.value)}
                              className="w-full rounded-md border border-[#E7E5E4] px-2 py-1 text-sm"
                            />
                          ) : item.description}
                        </div>
                        {(item.sku || item.supplier || item.brand || item.productUrl || item.retailPriceInclVat) && (
                          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-[#78716C]">
                            {item.sku && <span>SKU: {item.sku}</span>}
                            {(item.brand || item.supplier) && (
                              <span>{item.brand ? item.brand : item.supplier}{item.brand && item.supplier ? ` • ${item.supplier}` : ''}</span>
                            )}
                            {item.retailPriceInclVat != null && (
                              <span>
                                Supplier inc. VAT: £{formatCurrency(item.retailPriceInclVat)}
                              </span>
                            )}
                            {item.productUrl && (
                              <span>
                                <a
                                  href={item.productUrl}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="text-[#D4650A] hover:underline"
                                >
                                  View product
                                </a>
                              </span>
                            )}
                          </div>
                        )}
                        {isBoqEditing ? (
                          <div className="mt-1">
                            <input
                              value={item.notes ?? ''}
                              onChange={(e) => handleBoqDraftChange(item.id, 'notes', e.target.value)}
                              placeholder="Notes"
                              className="w-full rounded-md border border-[#E7E5E4] px-2 py-1 text-[11px]"
                            />
                          </div>
                        ) : item.notes && <div className="text-[11px] text-[#78716C]">{item.notes}</div>}

                        {!isBoqEditing && (
                          <div className="mt-2 grid grid-cols-2 gap-1 text-[11px] text-[#57534E] md:hidden">
                            <span>Qty: {item.quantity} {item.unit}</span>
                            <span className="text-right">Labour: £{formatCurrencySafe(item.labourTotal)}</span>
                            <span>Materials: £{formatCurrencySafe(item.materialTotal)}</span>
                            <span className="text-right">Plant: £{formatCurrencySafe(item.plantTotal)}</span>
                            <span className="col-span-2 text-right font-semibold text-[#1C1917]">
                              Total: £{formatCurrencySafe(item.labourTotal + item.materialTotal + item.plantTotal)}
                            </span>
                          </div>
                        )}
                      </td>
                      <td className="py-2.5 text-sm text-[#57534E] text-right whitespace-nowrap">
                        {isBoqEditing ? (
                          <input
                            type="number"
                            min={0}
                            step="0.1"
                            value={item.quantity}
                            onChange={(e) => handleBoqDraftChange(item.id, 'quantity', e.target.value)}
                            className="w-20 rounded-md border border-[#E7E5E4] px-2 py-1 text-right text-sm"
                          />
                        ) : <>{item.quantity} {item.unit}</>}
                      </td>
                      <td className="py-2.5 text-sm text-[#57534E] text-right whitespace-nowrap">
                        {isBoqEditing ? (
                          <input
                            type="number"
                            min={0}
                            step="0.01"
                            value={item.labourTotal}
                            onChange={(e) => handleBoqDraftChange(item.id, 'labourTotal', e.target.value)}
                            className="w-24 rounded-md border border-[#E7E5E4] px-2 py-1 text-right text-sm"
                          />
                        ) : <>£{formatCurrencySafe(item.labourTotal)}</>}
                      </td>
                      <td className="py-2.5 text-sm text-[#57534E] text-right whitespace-nowrap">
                        {isBoqEditing ? (
                          <input
                            type="number"
                            min={0}
                            step="0.01"
                            value={item.materialTotal}
                            onChange={(e) => handleBoqDraftChange(item.id, 'materialTotal', e.target.value)}
                            className="w-24 rounded-md border border-[#E7E5E4] px-2 py-1 text-right text-sm"
                          />
                        ) : <>£{formatCurrencySafe(item.materialTotal)}</>}
                      </td>
                      <td className="py-2.5 text-sm text-[#57534E] text-right whitespace-nowrap">
                        {isBoqEditing ? (
                          <input
                            type="number"
                            min={0}
                            step="0.01"
                            value={item.plantTotal}
                            onChange={(e) => handleBoqDraftChange(item.id, 'plantTotal', e.target.value)}
                            className="w-24 rounded-md border border-[#E7E5E4] px-2 py-1 text-right text-sm"
                          />
                        ) : <>£{formatCurrencySafe(item.plantTotal)}</>}
                      </td>
                      <td className="py-2.5 text-sm font-medium text-[#1C1917] text-right whitespace-nowrap">
                        £{formatCurrencySafe(item.labourTotal + item.materialTotal + item.plantTotal)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
              <div className="mt-4 pt-4 border-t border-[#F0EFEA] space-y-1">
                <div className="flex justify-between text-sm text-[#57534E]"><span>Subtotal</span><span>£{formatCurrency(boq.subtotal)}</span></div>
                <div className="flex justify-between text-sm text-[#57534E]"><span>VAT ({(boq.vatRate * 100).toFixed(0)}%)</span><span>£{formatCurrency(boq.vatAmount)}</span></div>
                <div className="flex justify-between text-lg font-bold text-[#1C1917]"><span>Total</span><span>£{formatCurrency(boq.total)}</span></div>
              </div>
              {boq.warnings.length > 0 && (
                <div className="mt-4 p-3 bg-[#FEF2F2] rounded-lg text-xs text-[#DC2626]">
                  {boq.warnings.map((warning) => (
                    <div key={warning}>• {warning}</div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* AI Panel */}
          {quote.aiGenerated && (
            <div className="bg-[#F5F3FF] rounded-xl border border-[#EDE9FE] p-5">
              <div className="flex items-center gap-2 mb-3">
                <Sparkles className="w-4 h-4 text-[#7C3AED]" />
                <span className="text-sm font-semibold text-[#7C3AED]">AI Generated</span>
              </div>
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div><span className="text-[#78716C]">Confidence: </span><span className="font-semibold text-[#1C1917]">{quote.aiConfidenceScore}%</span></div>
                <div><span className="text-[#78716C]">Model: </span><span className="font-semibold text-[#1C1917]">GPT-4o</span></div>
                <div><span className="text-[#78716C]">Generated: </span><span className="font-semibold text-[#1C1917]">{new Date(quote.createdAt).toLocaleString('en-GB')}</span></div>
                <div><span className="text-[#78716C]">Validation: </span><span className="font-semibold text-[#16A34A]">All prices validated</span></div>
              </div>
              <div className="mt-3 h-2 bg-white rounded-full overflow-hidden">
                <div className="h-full bg-[#7C3AED] rounded-full transition-all" style={{ width: `${quote.aiConfidenceScore}%` }} />
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
