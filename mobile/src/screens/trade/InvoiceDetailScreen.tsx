import { useMemo, useState } from "react";
import { ScrollView, StyleSheet, TextInput, View } from "react-native";
import { ApiInvoice, ApiInvoiceLineItem, UpdateInvoiceInput } from "../../api/invoices";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Icon } from "../../components/ui/Icon";
import { IconButton } from "../../components/ui/IconButton";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { ApiError } from "../../lib/apiClient";
import { formatMoneyGBP } from "../../lib/format";
import { Invoice, InvoiceStatus } from "../../types";

type EditableLineItem = {
  id: string;
  description: string;
  qty: string;
  unitPrice: string;
};

function toEditable(items: ApiInvoiceLineItem[]): EditableLineItem[] {
  return items.map((item) => ({
    id: item.id,
    description: item.description,
    qty: String(parseFloat(item.quantity) || 0),
    unitPrice: (parseFloat(item.unitPrice) || 0).toFixed(2),
  }));
}

function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.detail;
  if (err instanceof Error) return err.message;
  return fallback;
}

export type InvoiceDetailScreenProps = {
  invoice: Invoice;
  onClose: () => void;
  onViewRevenue?: () => void;
  /** When provided (connected mode), called to persist payment on the backend. */
  onMarkPaid?: () => Promise<void>;
  markingPaid?: boolean;
  /** When provided (connected mode), sends/re-sends the invoice and notifies the customer. */
  onSendInvoice?: () => Promise<void>;
  sendingInvoice?: boolean;
  /** Raw line items from the API, used to seed the inline line-item editor. */
  lineItems?: ApiInvoiceLineItem[];
  /** VAT rate applied to the invoice (derived from the API amounts). */
  vatRate?: number;
  /** When provided (connected mode), PATCHes the replacement line items. */
  onSaveLineItems?: (
    lineItems: NonNullable<UpdateInvoiceInput["lineItems"]>
  ) => Promise<ApiInvoice>;
  savingLineItems?: boolean;
};

export function InvoiceDetailScreen({
  invoice,
  onClose,
  onViewRevenue,
  onMarkPaid,
  markingPaid,
  onSendInvoice,
  sendingInvoice,
  lineItems,
  vatRate = 0.2,
  onSaveLineItems,
  savingLineItems,
}: InvoiceDetailScreenProps) {
  const [status, setStatus] = useState<InvoiceStatus>(invoice.status);
  const [paidAt, setPaidAt] = useState<string | undefined>(invoice.paidAt);
  const [sendError, setSendError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [editItems, setEditItems] = useState<EditableLineItem[]>([]);
  const [editError, setEditError] = useState<string | null>(null);
  /** Latest total from the PATCH response, shown until the refetch lands. */
  const [savedTotal, setSavedTotal] = useState<number | null>(null);

  const isPaid = status === "paid";
  const isSent = status === "sent";
  const isOverdue = status === "overdue";

  const canEdit = !!onSaveLineItems && !!lineItems;
  const displayAmount = savedTotal ?? invoice.amount;

  const editTotals = useMemo(() => {
    const subtotal = editItems.reduce((sum, item) => {
      const qty = parseFloat(item.qty) || 0;
      const price = parseFloat(item.unitPrice) || 0;
      return sum + qty * price;
    }, 0);
    const vat = subtotal * vatRate;
    return { subtotal, vat, total: subtotal + vat };
  }, [editItems, vatRate]);

  const markPaid = async () => {
    if (onMarkPaid) {
      await onMarkPaid();
    }
    const now = new Date().toISOString();
    setStatus("paid");
    setPaidAt(now);
  };

  /** Used by both "Send invoice" and "Send reminder" — the backend re-notifies. */
  const sendInvoice = async () => {
    if (!onSendInvoice) {
      onClose();
      return;
    }
    setSendError(null);
    try {
      await onSendInvoice();
      onClose();
    } catch (err) {
      setSendError(errorMessage(err, "Couldn't send the invoice. Please try again."));
    }
  };

  const startEditing = () => {
    setEditItems(toEditable(lineItems ?? []));
    setEditError(null);
    setEditing(true);
  };

  const updateItem = (id: string, field: keyof EditableLineItem, value: string) => {
    setEditItems((prev) =>
      prev.map((item) => (item.id === id ? { ...item, [field]: value } : item))
    );
  };

  const addLine = () => {
    setEditItems((prev) => [
      ...prev,
      { id: `new-${Date.now()}`, description: "", qty: "1", unitPrice: "0.00" },
    ]);
  };

  const removeItem = (id: string) => {
    setEditItems((prev) => prev.filter((item) => item.id !== id));
  };

  const saveLineItems = async () => {
    if (!onSaveLineItems) return;
    setEditError(null);
    try {
      const updated = await onSaveLineItems(
        editItems.map((item) => ({
          description: item.description,
          quantity: parseFloat(item.qty) || 0,
          unitPrice: parseFloat(item.unitPrice) || 0,
        }))
      );
      const total = parseFloat(updated.total);
      setSavedTotal(Number.isFinite(total) ? total : null);
      setEditing(false);
    } catch (err) {
      setEditError(errorMessage(err, "Couldn't save your changes."));
    }
  };

  return (
    <Screen>
      <Header title="Invoice" onBack={onClose} />

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
      >
        <View style={[styles.card, styles.totalCard]}>
          <Text variant="caption" color="secondary">
            {invoice.title}
          </Text>
          <Text variant="title" weight="bold" testID="invoice-total">
            {formatMoneyGBP(displayAmount)}
          </Text>
          <View style={[styles.badge, { backgroundColor: statusColor(status) }]}>
            <Text variant="caption" color="secondary">
              {status.toUpperCase()}
            </Text>
          </View>
        </View>

        {isPaid && (
          <View style={styles.paidBanner} testID="invoice-paid-banner">
            <View style={styles.paidIcon}>
              <Icon name="checkmark" size={22} color="#FFFFFF" />
            </View>
            <View style={{ flex: 1 }}>
              <Text variant="body" weight="semibold" style={{ color: "#065F46" }}>
                Payment received
              </Text>
              <Text variant="caption" color="secondary">
                {formatMoneyGBP(displayAmount)} paid by {invoice.customerName}
              </Text>
            </View>
          </View>
        )}

        <View style={styles.card}>
          <Text variant="body" weight="semibold">
            Customer
          </Text>
          <Text variant="body">{invoice.customerName}</Text>
        </View>

        {editing ? (
          <>
            {editItems.map((item, index) => (
              <View
                key={item.id}
                className="rounded-2xl border border-slate-200 bg-white p-3 gap-2"
              >
                <View className="flex-row items-center justify-between">
                  <Text variant="caption" color="secondary">
                    Line {index + 1}
                  </Text>
                  <IconButton
                    icon="close"
                    size={18}
                    color="#6B7280"
                    onPress={() => removeItem(item.id)}
                  />
                </View>

                <TextInput
                  testID={`invoice-line-description-${index}`}
                  className="h-10 rounded-lg border border-slate-200 px-3 text-sm text-slate-900"
                  value={item.description}
                  onChangeText={(value) => updateItem(item.id, "description", value)}
                  placeholder="Description"
                />

                <View className="flex-row flex-wrap gap-2">
                  <View className="min-w-[70px] flex-1">
                    <Text variant="caption" color="secondary">
                      Qty
                    </Text>
                    <TextInput
                      testID={`invoice-line-qty-${index}`}
                      className="h-9 rounded-lg border border-slate-200 px-3 text-sm text-slate-900"
                      value={item.qty}
                      onChangeText={(value) => updateItem(item.id, "qty", value)}
                      keyboardType="decimal-pad"
                    />
                  </View>
                  <View className="min-w-[100px] flex-[1.5]">
                    <Text variant="caption" color="secondary">
                      Price (£)
                    </Text>
                    <TextInput
                      testID={`invoice-line-price-${index}`}
                      className="h-9 rounded-lg border border-slate-200 px-3 text-sm text-slate-900"
                      value={item.unitPrice}
                      onChangeText={(value) => updateItem(item.id, "unitPrice", value)}
                      keyboardType="decimal-pad"
                    />
                  </View>
                </View>
              </View>
            ))}

            <Button testID="invoice-add-line" title="+ Add line item" variant="outline" onPress={addLine} />

            {editError && (
              <View className="rounded-2xl bg-amber-50 p-3">
                <Text testID="invoice-edit-error" variant="caption" color="warning">
                  {editError}
                </Text>
              </View>
            )}

            <View className="flex-row items-end justify-between gap-3 rounded-xl bg-slate-100 p-3">
              <View>
                <Text variant="caption" color="secondary">
                  Subtotal
                </Text>
                <Text variant="caption" color="secondary">
                  {formatMoneyGBP(editTotals.subtotal)}
                </Text>
              </View>
              <View>
                <Text variant="caption" color="secondary">
                  VAT ({(vatRate * 100).toFixed(0)}%)
                </Text>
                <Text variant="caption" color="secondary">
                  {formatMoneyGBP(editTotals.vat)}
                </Text>
              </View>
              <View className="items-end">
                <Text variant="caption" color="secondary">
                  Total
                </Text>
                <Text variant="body" weight="bold" testID="invoice-edit-total">
                  {formatMoneyGBP(editTotals.total)}
                </Text>
              </View>
            </View>
          </>
        ) : (
          lineItems &&
          lineItems.length > 0 && (
            <View style={styles.card}>
              <Text variant="body" weight="semibold">
                Line items
              </Text>
              {lineItems.map((item) => (
                <View key={item.id} style={styles.lineRow}>
                  <View style={{ flex: 1 }}>
                    <Text variant="body">{item.description}</Text>
                    <Text variant="caption" color="secondary">
                      {parseFloat(item.quantity) || 0} × {formatMoneyGBP(parseFloat(item.unitPrice) || 0)}
                    </Text>
                  </View>
                  <Text variant="body">{formatMoneyGBP(parseFloat(item.total) || 0)}</Text>
                </View>
              ))}
            </View>
          )
        )}

        <View style={styles.card}>
          <Text variant="body" weight="semibold">
            Dates
          </Text>
          <Text variant="body" color="secondary">
            Sent {invoice.sentAt ? new Date(invoice.sentAt).toLocaleDateString() : "—"}
          </Text>
          <Text variant="body" color="secondary">
            Due {new Date(invoice.dueDate).toLocaleDateString()}
          </Text>
          {paidAt && (
            <Text variant="body" color="secondary">
              Paid {new Date(paidAt).toLocaleDateString()}
            </Text>
          )}
        </View>

        <View style={styles.card}>
          <Text variant="body" weight="semibold">
            Payment method
          </Text>
          <Text variant="body" color="secondary">
            Bank transfer · details from your invoice email
          </Text>
        </View>
      </ScrollView>

      <View style={styles.footer}>
        {sendError && (
          <View className="rounded-2xl bg-amber-50 p-3">
            <Text testID="invoice-send-error" variant="caption" color="warning">
              {sendError}
            </Text>
          </View>
        )}
        {editing ? (
          <>
            <Button
              testID="invoice-save"
              title={savingLineItems ? "Saving…" : "Save changes"}
              disabled={savingLineItems}
              onPress={() => void saveLineItems()}
            />
            <Button
              title="Cancel"
              variant="outline"
              disabled={savingLineItems}
              onPress={() => setEditing(false)}
            />
          </>
        ) : (
          <>
            {isPaid && (
              <>
                <Button
                  testID="invoice-view-revenue"
                  title="View revenue dashboard"
                  onPress={() => onViewRevenue?.()}
                />
                <Button title="Send receipt" variant="outline" onPress={onClose} />
              </>
            )}
            {isSent && (
              <>
                <Button
                  testID="invoice-mark-paid"
                  title={markingPaid ? "Marking paid…" : "Mark as paid"}
                  disabled={markingPaid || sendingInvoice}
                  onPress={markPaid}
                />
                <Button
                  testID="invoice-send-reminder"
                  title={sendingInvoice ? "Sending…" : "Send reminder"}
                  variant="outline"
                  disabled={sendingInvoice}
                  onPress={() => void sendInvoice()}
                />
              </>
            )}
            {(isOverdue || status === "draft") && (
              <>
                <Button
                  testID="invoice-send"
                  title={sendingInvoice ? "Sending…" : "Send invoice"}
                  disabled={sendingInvoice}
                  onPress={() => void sendInvoice()}
                />
                {canEdit && (
                  <Button
                    testID="invoice-edit"
                    title="Edit invoice"
                    variant="outline"
                    onPress={startEditing}
                  />
                )}
              </>
            )}
          </>
        )}
      </View>
    </Screen>
  );
}

function statusColor(status: Invoice["status"]): string {
  switch (status) {
    case "paid":
      return "#D1FAE5";
    case "sent":
      return "#DBEAFE";
    case "overdue":
      return "#FEE2E2";
    default:
      return "#FEF3C7";
  }
}

const styles = StyleSheet.create({
  scroll: {
    flex: 1,
  },
  scrollContent: {
    flexGrow: 1,
    gap: 16,
    paddingBottom: 24,
  },
  card: {
    padding: 16,
    borderRadius: 16,
    backgroundColor: "#F3F4F6",
    gap: 8,
  },
  totalCard: {
    alignItems: "center",
    paddingVertical: 24,
    backgroundColor: "#EFF6FF",
  },
  lineRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  paidBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    padding: 16,
    borderRadius: 16,
    backgroundColor: "#ECFDF5",
    borderWidth: 1,
    borderColor: "#A7F3D0",
  },
  paidIcon: {
    height: 40,
    width: 40,
    borderRadius: 20,
    backgroundColor: "#10B981",
    alignItems: "center",
    justifyContent: "center",
  },
  badge: {
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 2,
    marginTop: 8,
  },
  footer: {
    gap: 12,
    paddingVertical: 16,
    borderTopWidth: 1,
    borderTopColor: "#E5E7EB",
  },
});
