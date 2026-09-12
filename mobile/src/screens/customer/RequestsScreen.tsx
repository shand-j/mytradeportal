import { useMemo, useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, TextInput, View } from "react-native";
import * as ImagePicker from "expo-image-picker";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { IconButton } from "../../components/ui/IconButton";
import { Icon } from "../../components/ui/Icon";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { CustomerQuoteRequestFlow } from "./CustomerQuoteRequestFlow";
import { NotificationBell } from "../../components/notifications/NotificationBell";
import { useBusiness } from "../../theme/ThemeProvider";
import { useMyRequests, CustomerRequest } from "../../api/quoteRequests";
import { useAcceptCustomerQuote, useRejectCustomerQuote } from "../../api/quotes";
import { useCreateCustomerAppointment } from "../../api/appointments";
import { StagedPhoto, uploadCustomerPhotos } from "../../api/uploads";
import type { Quote, QuoteStatus } from "../../types";

type CustomerQuoteStatus = "awaiting_review" | "open" | "accepted" | "rejected" | "expired";

const STATUS_MAP: Record<QuoteStatus, CustomerQuoteStatus> = {
  draft: "awaiting_review",
  sent: "open",
  accepted: "accepted",
  rejected: "rejected",
  expired: "expired",
};

const BADGE_COLORS: Record<
  CustomerQuoteStatus,
  { background: string; border: string; text: string; label: string }
> = {
  awaiting_review: {
    label: "AWAITING REVIEW",
    background: "#F3F4F6",
    border: "#E5E7EB",
    text: "#374151",
  },
  open: {
    label: "OPEN",
    background: "#F2F5F6",
    border: "#C3CFD5",
    text: "#0F1E26",
  },
  accepted: {
    label: "ACCEPTED",
    background: "#ECFDF5",
    border: "#A7F3D0",
    text: "#065F46",
  },
  rejected: {
    label: "REJECTED",
    background: "#FEF2F2",
    border: "#FECACA",
    text: "#B91C1C",
  },
  expired: {
    label: "EXPIRED",
    background: "#F3F4F6",
    border: "#E5E7EB",
    text: "#6B7280",
  },
};

function StatusBadge({ status }: { status: CustomerQuoteStatus }) {
  const colors = BADGE_COLORS[status];
  return (
    <View
      className="rounded-lg border px-2 py-1"
      style={{ backgroundColor: colors.background, borderColor: colors.border }}
    >
      <Text variant="caption" weight="semibold" style={{ color: colors.text, fontSize: 10 }}>
        {colors.label}
      </Text>
    </View>
  );
}

function BookDateView({
  quote,
  acceptanceNote,
  onBack,
  onConfirmBooking,
}: {
  quote: Quote;
  /** Post-acceptance assurance line, shown under the "Quote accepted" card. */
  acceptanceNote?: string | null;
  onBack: () => void;
  onConfirmBooking: (date: string, timeSlot: string) => Promise<void>;
}) {
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [selectedTime, setSelectedTime] = useState<string | null>(null);

  const subtotal = useMemo(
    () =>
      quote.lineItems.reduce((sum, item) => {
        const qty = parseFloat(item.qty) || 0;
        const price = parseFloat(item.unitPrice) || 0;
        return sum + qty * price;
      }, 0),
    [quote]
  );
  const total = subtotal * (1 + quote.vatRate);

  const nextDays = useMemo(() => {
    const days = [];
    for (let i = 1; i <= 7; i++) {
      const d = new Date();
      d.setDate(d.getDate() + i);
      days.push(d);
    }
    return days;
  }, []);

  const timeSlots = ["08:00 - 10:00", "10:00 - 12:00", "12:00 - 14:00", "14:00 - 16:00", "16:00 - 18:00"];
  const dayLabels = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  return (
    <Screen>
      <Header title="Book a date" onBack={onBack} />

      <ScrollView className="flex-1" contentContainerStyle={{ gap: 16, paddingBottom: 40 }}>
        <View className="gap-1 rounded-2xl border border-primary-200 bg-primary-50 p-4">
          <Text variant="caption" color="primary">
            Quote accepted
          </Text>
          <Text variant="body" weight="semibold">
            {quote.title}
          </Text>
          <Text variant="title" weight="bold" color="primary">
            £{total.toFixed(2)}
          </Text>
          {acceptanceNote ? (
            <Text variant="caption" color="secondary">
              {acceptanceNote}
            </Text>
          ) : null}
        </View>

        <View className="gap-3 rounded-2xl border border-slate-200 bg-white p-4">
          <Text variant="body" weight="semibold">
            Pick a day
          </Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
            {nextDays.map((date, index) => {
              const label = `${dayLabels[date.getDay()]} ${date.getDate()}`;
              const active = selectedDate === label;
              return (
                <Pressable
                  key={label}
                  testID={`book-day-${index}`}
                  onPress={() => setSelectedDate(label)}
                >
                  <View
                    className="h-16 w-12 items-center justify-center rounded-xl border"
                    style={{
                      backgroundColor: active ? "#F2F5F6" : "#F8FAFC",
                      borderColor: active ? "#0F1E26" : "#E2E8F0",
                    }}
                  >
                    <Text variant="caption" color={active ? "primary" : "secondary"}>
                      {dayLabels[date.getDay()]}
                    </Text>
                    <Text
                      variant="body"
                      weight={active ? "bold" : "normal"}
                      color={active ? "primary" : "text"}
                    >
                      {date.getDate()}
                    </Text>
                  </View>
                </Pressable>
              );
            })}
          </ScrollView>
        </View>

        <View className="gap-3 rounded-2xl border border-slate-200 bg-white p-4">
          <Text variant="body" weight="semibold">
            Pick a time
          </Text>
          <View className="flex-row flex-wrap gap-2">
            {timeSlots.map((slot, index) => {
              const active = selectedTime === slot;
              return (
                <Pressable
                  key={slot}
                  testID={`book-time-${index}`}
                  onPress={() => setSelectedTime(slot)}
                >
                  <View
                    className="rounded-xl border px-4 py-2"
                    style={{
                      backgroundColor: active ? "#F2F5F6" : "#F8FAFC",
                      borderColor: active ? "#0F1E26" : "#E2E8F0",
                    }}
                  >
                    <Text
                      variant="caption"
                      weight={active ? "semibold" : "normal"}
                      color={active ? "primary" : "secondary"}
                    >
                      {slot}
                    </Text>
                  </View>
                </Pressable>
              );
            })}
          </View>
        </View>

        <Button
          testID="booking-confirm"
          title="Confirm booking"
          onPress={() => void onConfirmBooking(selectedDate!, selectedTime!)}
          disabled={!selectedDate || !selectedTime}
        />
      </ScrollView>
    </Screen>
  );
}

function RejectQuoteView({
  quote,
  onBack,
  onConfirm,
}: {
  quote: Quote;
  onBack: () => void;
  onConfirm: (reason: string) => void;
}) {
  const { business } = useBusiness();
  const [reason, setReason] = useState("");

  return (
    <Screen>
      <Header title="Decline quote" onBack={onBack} />

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView
          className="flex-1"
          contentContainerStyle={{ gap: 16, paddingBottom: 40 }}
          keyboardShouldPersistTaps="handled"
        >
        <Text variant="body" color="secondary">
          You can let {business?.name ?? "your electrician"} know why you're declining this quote.
        </Text>

        <View className="gap-3 rounded-2xl border border-slate-200 bg-white p-4">
          <Text variant="body" weight="semibold">
            {quote.title}
          </Text>
          <TextInput
            className="min-h-20 rounded-xl border border-slate-200 bg-slate-50 p-3 text-base text-slate-900"
            value={reason}
            onChangeText={setReason}
            placeholder="Reason (optional)"
            multiline
            numberOfLines={3}
            maxLength={250}
          />
          <Text variant="caption" color="secondary" align="right">
            {reason.length}/250
          </Text>
        </View>

        <Button title="Confirm decline" variant="outline" onPress={() => onConfirm(reason)} />
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

function CustomerQuoteView({
  quote,
  status,
  preferredDates,
  acceptanceNote,
  onBack,
  onAccept,
  onReject,
  onRequestChanges,
  onBook,
}: {
  quote: Quote;
  status: CustomerQuoteStatus;
  /** Preferred visit dates from the source quote request (empty when none). */
  preferredDates: string[];
  /** Post-acceptance assurance line, shown in the accepted card. */
  acceptanceNote: string | null;
  onBack: () => void;
  onAccept: (preferredDates?: string[]) => void;
  onReject: () => void;
  onRequestChanges: () => void;
  onBook: () => void;
}) {
  const { business } = useBusiness();
  const [confirmingDates, setConfirmingDates] = useState(false);
  const [selectedDates, setSelectedDates] = useState<string[]>([]);
  const subtotal = useMemo(
    () =>
      quote.lineItems.reduce((sum, item) => {
        const qty = parseFloat(item.qty) || 0;
        const price = parseFloat(item.unitPrice) || 0;
        return sum + qty * price;
      }, 0),
    [quote]
  );
  const vat = subtotal * quote.vatRate;
  const total = subtotal + vat;
  const isOpen = status === "open";
  const isAccepted = status === "accepted";
  const isRejected = status === "rejected";
  const isAwaiting = status === "awaiting_review";
  const isExpired = status === "expired";

  const toggleDate = (date: string) => {
    setSelectedDates((prev) =>
      prev.includes(date) ? prev.filter((d) => d !== date) : [...prev, date]
    );
  };

  return (
    <Screen>
      <Header title={quote.title} onBack={onBack} />

      <ScrollView className="flex-1" contentContainerStyle={{ gap: 16, paddingBottom: 40 }}>
        <View className="gap-3 rounded-2xl border border-slate-200 bg-white p-4">
          <View className="flex-row items-center justify-between">
            <Text variant="body" weight="semibold" numberOfLines={1} style={{ flex: 1 }}>
              {business?.name ?? "Your electrician"}
            </Text>
            <StatusBadge status={status} />
          </View>
          <Text variant="caption" color="secondary">
            {quote.postcode} · Valid until{" "}
            {quote.expiresAt ? new Date(quote.expiresAt).toLocaleDateString() : "—"}
          </Text>
        </View>

        <View className="gap-3 rounded-2xl border border-slate-200 bg-white p-4">
          {quote.lineItems.map((item) => (
            <View key={item.id} className="flex-row items-center justify-between gap-2">
              <Text variant="body" style={{ flex: 1 }}>
                {item.description}
              </Text>
              <Text variant="body" weight="semibold">
                £{((parseFloat(item.qty) || 0) * (parseFloat(item.unitPrice) || 0)).toFixed(2)}
              </Text>
            </View>
          ))}

          <View className="my-1 h-px bg-slate-200" />

          <View className="flex-row items-center justify-between">
            <Text variant="caption" color="secondary">
              Subtotal
            </Text>
            <Text variant="caption" color="secondary">
              £{subtotal.toFixed(2)}
            </Text>
          </View>
          <View className="flex-row items-center justify-between">
            <Text variant="caption" color="secondary">
              VAT ({(quote.vatRate * 100).toFixed(0)}%)
            </Text>
            <Text variant="caption" color="secondary">
              £{vat.toFixed(2)}
            </Text>
          </View>
          <View className="flex-row items-center justify-between">
            <Text variant="body" weight="bold">
              Total
            </Text>
            <Text variant="title" weight="bold" color="primary">
              £{total.toFixed(2)}
            </Text>
          </View>
        </View>

        <View className="gap-2 rounded-2xl border border-slate-200 bg-white p-4">
          <Text variant="body" weight="semibold">
            Assumptions
          </Text>
          {quote.assumptions.map((assumption, index) => (
            <Text key={index} variant="caption" color="secondary">
              • {assumption}
            </Text>
          ))}
        </View>

        <View className="gap-2">
          {isOpen && preferredDates.length > 0 && confirmingDates && (
            <View
              testID="quote-reconfirm-dates"
              className="gap-3 rounded-2xl border border-slate-200 bg-white p-4"
            >
              <Text variant="body" weight="semibold">
                Confirm your preferred dates — the electrician will try to accommodate them.
              </Text>
              <Text variant="caption" color="secondary">
                Tap any date that no longer works to deselect it.
              </Text>
              <View className="flex-row flex-wrap gap-2">
                {preferredDates.map((date, index) => {
                  const active = selectedDates.includes(date);
                  return (
                    <Pressable
                      key={date}
                      testID={`reconfirm-date-${index}`}
                      onPress={() => toggleDate(date)}
                    >
                      <View
                        className="rounded-xl border px-4 py-2"
                        style={{
                          backgroundColor: active ? "#F2F5F6" : "#F8FAFC",
                          borderColor: active ? "#0F1E26" : "#E2E8F0",
                        }}
                      >
                        <Text
                          variant="caption"
                          weight={active ? "semibold" : "normal"}
                          color={active ? "primary" : "secondary"}
                        >
                          {date}
                        </Text>
                      </View>
                    </Pressable>
                  );
                })}
              </View>
            </View>
          )}

          {isOpen && (
            <>
              {preferredDates.length > 0 ? (
                confirmingDates ? (
                  <>
                    <Button
                      testID="quote-confirm-accept"
                      title="Confirm acceptance"
                      onPress={() => onAccept(selectedDates)}
                    />
                    <Button
                      title="Back"
                      variant="ghost"
                      onPress={() => setConfirmingDates(false)}
                    />
                  </>
                ) : (
                  <Button
                    testID="quote-accept"
                    title="Accept quote"
                    onPress={() => {
                      setSelectedDates(preferredDates);
                      setConfirmingDates(true);
                    }}
                  />
                )
              ) : (
                <Button testID="quote-accept" title="Accept quote" onPress={() => onAccept()} />
              )}
              <Button title="Reject quote" variant="outline" onPress={onReject} />
              <Button title="Request changes" variant="ghost" onPress={onRequestChanges} />
            </>
          )}

          {isAccepted && (
            <View className="gap-2 rounded-2xl border border-success-200 bg-success-50 p-4">
              <Text variant="body" weight="semibold" color="success">
                Quote accepted
              </Text>
              {acceptanceNote ? (
                <Text variant="body" color="secondary">
                  {acceptanceNote}
                </Text>
              ) : null}
              <Text variant="body" color="secondary">
                Choose a date and time for the work.
              </Text>
              <Button title="Book a date" onPress={onBook} />
            </View>
          )}

          {isRejected && (
            <View className="gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <Text variant="body" weight="semibold">
                Quote declined
              </Text>
              <Text variant="body" color="secondary">
                Let your electrician know if your plans change.
              </Text>
              <Button title="Request a revised quote" variant="outline" onPress={onRequestChanges} />
            </View>
          )}

          {isAwaiting && (
            <View className="gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <Text variant="body" weight="semibold">
                Quote request received
              </Text>
              <Text variant="body" color="secondary">
                Your electrician is preparing your quote. You'll be notified when it's ready.
              </Text>
              <Button title="Request changes" variant="outline" onPress={onRequestChanges} />
            </View>
          )}

          {isExpired && (
            <View className="gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <Text variant="body" weight="semibold">
                Quote expired
              </Text>
              <Text variant="body" color="secondary">
                This quote is no longer valid. Request a new quote if you still need the work.
              </Text>
              <Button title="Request a revised quote" variant="outline" onPress={onRequestChanges} />
            </View>
          )}
        </View>
      </ScrollView>
    </Screen>
  );
}

export type RequestsScreenProps = {
  navigation: {
    navigate: (name: string, params?: Record<string, unknown>) => void;
  };
};

const REQUEST_BADGE: Record<CustomerRequest["status"], CustomerQuoteStatus> = {
  awaiting_review: "awaiting_review",
  open: "open",
  converted: "accepted",
  closed: "expired",
};

/**
 * Lets the customer attach photos to an existing quote request — the same
 * upload point as the intake flow's Photos step, available after submission
 * (e.g. when the electrician or AI assistant asks for more photos).
 */
function AddRequestPhotos({ requestId }: { requestId: string }) {
  const queryClient = useQueryClient();
  const [uploading, setUploading] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [feedbackIsError, setFeedbackIsError] = useState(false);

  const addPhotos = async () => {
    setFeedback(null);
    setFeedbackIsError(false);
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      setFeedback("Photo library access denied");
      setFeedbackIsError(true);
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      quality: 0.7,
      allowsMultipleSelection: true,
    });
    if (result.canceled || result.assets.length === 0) return;
    const stamp = Date.now();
    const photos: StagedPhoto[] = result.assets.map((asset, index) => ({
      uri: asset.uri,
      name: asset.fileName ?? `photo-${stamp}-${index}.jpg`,
      type: asset.mimeType ?? "image/jpeg",
      sizeBytes: asset.fileSize,
    }));
    setUploading(true);
    try {
      const { uploaded, failed } = await uploadCustomerPhotos(requestId, photos);
      if (failed > 0) {
        setFeedback(
          `${uploaded} of ${photos.length} photos uploaded — ${failed} failed. Please try again.`
        );
        setFeedbackIsError(true);
      } else {
        setFeedback(`${uploaded} ${uploaded === 1 ? "photo" : "photos"} sent to your electrician.`);
      }
      queryClient.invalidateQueries({ queryKey: ["my-requests"] });
    } finally {
      setUploading(false);
    }
  };

  return (
    <View className="gap-1">
      <Button
        testID={`request-add-photos-${requestId}`}
        title={uploading ? "Uploading…" : "Add photos"}
        variant="outline"
        size="sm"
        disabled={uploading}
        onPress={() => void addPhotos()}
      />
      {feedback ? (
        <Text variant="caption" color={feedbackIsError ? "warning" : "secondary"}>
          {feedback}
        </Text>
      ) : null}
    </View>
  );
}

/** A card for a real (backend) customer quote request. */
function CustomerRequestCard({
  request,
  onPress,
}: {
  request: CustomerRequest;
  onPress?: () => void;
}) {
  const content = (
    <View testID={`request-card-${request.id}`} className="gap-2 rounded-2xl border border-slate-200 bg-white p-4">
      <View className="flex-row items-center justify-between gap-2">
        <Text variant="body" weight="semibold" numberOfLines={1} style={{ flex: 1 }}>
          {request.title}
        </Text>
        <StatusBadge status={REQUEST_BADGE[request.status]} />
      </View>
      {request.postcode ? (
        <Text variant="caption" color="secondary">
          {request.postcode}
        </Text>
      ) : null}
      <Text variant="caption" color="secondary">
        Submitted {new Date(request.createdAt).toLocaleDateString()}
      </Text>
      <AddRequestPhotos requestId={request.id} />
    </View>
  );

  if (!onPress) return content;
  return <Pressable onPress={onPress}>{content}</Pressable>;
}

function QuoteCard({
  quote,
  status,
  onPress,
}: {
  quote: Quote;
  status: CustomerQuoteStatus;
  onPress: () => void;
}) {
  const isAwaiting = status === "awaiting_review";
  const subtotal = useMemo(
    () =>
      quote.lineItems.reduce((sum, item) => {
        const qty = parseFloat(item.qty) || 0;
        const price = parseFloat(item.unitPrice) || 0;
        return sum + qty * price;
      }, 0),
    [quote]
  );
  const total = subtotal * (1 + quote.vatRate);

  return (
    <Pressable onPress={onPress} testID={`quote-card-${quote.id}`}>
      <View
        className="gap-2 rounded-2xl border p-4"
        style={{
          backgroundColor: status === "open" ? "#F2F5F6" : "#FFFFFF",
          borderColor: status === "open" ? "#C3CFD5" : "#E5E7EB",
        }}
      >
        <View className="flex-row items-center justify-between gap-2">
          <Text variant="body" weight="semibold" numberOfLines={1} style={{ flex: 1 }}>
            {quote.title}
          </Text>
          <StatusBadge status={status} />
        </View>

        <Text variant="caption" color="secondary">
          {quote.postcode}
        </Text>

        {isAwaiting ? (
          <Text variant="caption" color="secondary">
            Submitted {quote.sentAt ? new Date(quote.sentAt).toLocaleDateString() : "today"} ·
            Awaiting review
          </Text>
        ) : (
          <>
            <Text variant="title" weight="bold" color="primary">
              £{total.toFixed(2)}
            </Text>
            <Text variant="caption" color="secondary">
              Valid until{" "}
              {quote.expiresAt ? new Date(quote.expiresAt).toLocaleDateString() : "—"}
            </Text>
          </>
        )}
      </View>
    </Pressable>
  );
}

export function RequestsScreen({ navigation }: RequestsScreenProps) {
  const { business, theme } = useBusiness();
  const router = useRouter();

  const { requests: liveRequests, isConnected, isLoading } = useMyRequests();
  const acceptMutation = useAcceptCustomerQuote();
  const rejectMutation = useRejectCustomerQuote();
  const createAppointmentMutation = useCreateCustomerAppointment();

  const effectiveStatus = (quote: Quote): CustomerQuoteStatus => {
    return STATUS_MAP[quote.status] ?? "open";
  };
  const [requesting, setRequesting] = useState(false);
  const [view, setView] = useState<"list" | "detail" | "reject" | "booking">("list");
  const [selectedQuoteId, setSelectedQuoteId] = useState<string | null>(null);
  /** Assurance line shown right after an acceptance in this session. */
  const [acceptanceNote, setAcceptanceNote] = useState<string | null>(null);

  // Linked quotes from quote requests are the primary customer-facing view.
  const linkedQuotes = useMemo(
    () =>
      liveRequests
        .filter((req): req is CustomerRequest & { quote: Quote } => Boolean(req.quote))
        .map((req) => req.quote),
    [liveRequests]
  );

  /** Quotes still being generated or awaiting the electrician's review. */
  const generatingCount = useMemo(
    () =>
      liveRequests.filter(
        (req) => !req.quote || effectiveStatus(req.quote) === "awaiting_review"
      ).length,
    [liveRequests]
  );

  const selectedQuote = selectedQuoteId
    ? linkedQuotes.find((q) => q.id === selectedQuoteId) ?? null
    : null;

  const openMessagesForRequest = (requestId: string, initialText?: string) => {
    router.push({
      pathname: "/(customer)/messages",
      params: { quoteRequestId: requestId, ...(initialText ? { initialText } : {}) },
    });
  };

  const selectedRequestId = useMemo(() => {
    if (!selectedQuoteId) return null;
    const req = liveRequests.find((r) => r.quote?.id === selectedQuoteId);
    return req?.id ?? null;
  }, [liveRequests, selectedQuoteId]);

  const selectedPreferredDates = useMemo(() => {
    if (!selectedQuoteId) return [];
    return (
      liveRequests.find((r) => r.quote?.id === selectedQuoteId)?.preferredDates ?? []
    );
  }, [liveRequests, selectedQuoteId]);

  const handleAccept = async (quote: Quote, preferredDates?: string[]) => {
    await acceptMutation.mutateAsync({ id: quote.id, preferredDates });
    setAcceptanceNote(
      preferredDates && preferredDates.length > 0
        ? "Thanks — the electrician will try to accommodate your preferred dates."
        : "Your electrician will try to accommodate your preferred dates."
    );
    setView("booking");
  };

  const handleReject = async (quote: Quote, reason: string) => {
    await rejectMutation.mutateAsync(quote.id);
    console.log("Quote rejected:", quote.id, reason);
    setView("detail");
  };

  const handleConfirmBooking = async (quote: Quote, dateLabel: string, timeSlot: string) => {
    // Parse the selected day from "Mon 15" into a real date in the next 14 days.
    const dayNumber = parseInt(dateLabel.split(" ")[1], 10);
    const target = new Date();
    for (let i = 0; i < 14; i++) {
      const d = new Date();
      d.setDate(d.getDate() + i);
      if (d.getDate() === dayNumber) {
        target.setFullYear(d.getFullYear(), d.getMonth(), d.getDate());
        break;
      }
    }
    const startHour = parseInt(timeSlot.split(":")[0], 10);
    const start = new Date(target);
    start.setHours(startHour, 0, 0, 0);
    const end = new Date(start);
    end.setHours(startHour + 2, 0, 0, 0);

    await createAppointmentMutation.mutateAsync({
      title: quote.title,
      startAt: start.toISOString(),
      endAt: end.toISOString(),
      address: quote.postcode,
      notes: `Booking from accepted quote ${quote.id}`,
    });
    setView("list");
    router.push("/(customer)/calendar");
  };

  if (requesting) {
    return <CustomerQuoteRequestFlow onClose={() => setRequesting(false)} />;
  }

  if (view === "detail" && selectedQuote) {
    return (
      <CustomerQuoteView
        quote={selectedQuote}
        status={effectiveStatus(selectedQuote)}
        preferredDates={selectedPreferredDates}
        acceptanceNote={acceptanceNote}
        onBack={() => setView("list")}
        onAccept={(dates) => void handleAccept(selectedQuote, dates)}
        onReject={() => setView("reject")}
        onRequestChanges={() => {
          const requestId = selectedRequestId ?? liveRequests.find((r) => r.quote?.id === selectedQuoteId)?.id;
          if (requestId) openMessagesForRequest(requestId);
        }}
        onBook={() => setView("booking")}
      />
    );
  }

  if (view === "reject" && selectedQuote) {
    return (
      <RejectQuoteView
        quote={selectedQuote}
        onBack={() => setView("detail")}
        onConfirm={(reason) => void handleReject(selectedQuote, reason)}
      />
    );
  }

  if (view === "booking" && selectedQuote) {
    return (
      <BookDateView
        quote={selectedQuote}
        acceptanceNote={acceptanceNote}
        onBack={() => setView("detail")}
        onConfirmBooking={(date, timeSlot) => handleConfirmBooking(selectedQuote, date, timeSlot)}
      />
    );
  }

  return (
    <Screen>
      <Header
        title={business?.name ? `${business.name}` : "My quotes"}
        rightAction={
          <View className="flex-row items-center gap-1">
            <NotificationBell role="customer" />
            <IconButton
              icon="profile"
              size={24}
              color="#374151"
              onPress={() => navigation.navigate("Profile")}
              accessibilityLabel="Profile"
            />
          </View>
        }
      />

      <ScrollView className="flex-1" contentContainerStyle={{ gap: 16, paddingBottom: 40 }}>
        <Text variant="body" color="secondary">
          Track your quote requests and received quotes from {business?.name ?? "your electrician"}.
        </Text>

        <Pressable
          testID="customer-ai-banner"
          onPress={() => {
            const firstRequest = liveRequests[0];
            if (firstRequest) {
              openMessagesForRequest(firstRequest.id);
            } else {
              router.push("/(customer)/messages");
            }
          }}
        >
          <View
            className="flex-row items-center gap-3 rounded-2xl border p-4"
            style={{ borderColor: `${business?.primaryColor ?? theme.colors.primary}33`, backgroundColor: `${business?.primaryColor ?? theme.colors.primary}14` }}
          >
            <View
              className="h-9 w-9 items-center justify-center rounded-full"
              style={{ backgroundColor: business?.primaryColor ?? theme.colors.primary }}
            >
              <Icon name="sparkles" size={18} color="#FFFFFF" />
            </View>
            <View className="flex-1">
              <Text variant="body" weight="semibold">
                {business?.name ?? "Your electrician"} Assistant
              </Text>
              <Text variant="caption" color="secondary">
                A few quick questions to make your quote accurate — tap to reply
              </Text>
            </View>
            <Icon name="messages" size={18} color="#B27E00" />
          </View>
        </Pressable>

        {isLoading && (
          <Text variant="caption" color="secondary" align="center">
            Loading your quotes…
          </Text>
        )}

        {isConnected && generatingCount > 0 && (
          <View
            testID="quotes-generating-banner"
            className="gap-2 rounded-2xl border border-slate-200 bg-white p-4"
          >
            <Text variant="body" weight="semibold">
              {generatingCount} {generatingCount === 1 ? "quote" : "quotes"} generating
            </Text>
            <Text variant="caption" color="secondary">
              We'll notify you if we need anything else.
            </Text>
          </View>
        )}

        {isConnected &&
          liveRequests.map((req) =>
            req.quote && req.quoteStatus ? (
              <QuoteCard
                key={`quote-${req.quote.id}`}
                quote={req.quote}
                status={effectiveStatus(req.quote)}
                onPress={() => {
                  setAcceptanceNote(null);
                  setSelectedQuoteId(req.quote!.id);
                  setView("detail");
                }}
              />
            ) : (
              <CustomerRequestCard key={req.id} request={req} />
            )
          )}

        {isConnected && liveRequests.length === 0 && (
          <View className="gap-2 rounded-2xl border border-slate-200 bg-white p-4">
            <Text variant="body" weight="semibold">
              No requests yet
            </Text>
            <Text variant="caption" color="secondary">
              Tap “Request a new quote” to send your first request to{" "}
              {business?.name ?? "your electrician"} — we'll guide you through a few quick
              questions and notify you when your quote is ready.
            </Text>
          </View>
        )}

        {!isConnected && !isLoading && (
          <View className="gap-2 rounded-2xl border border-slate-200 bg-white p-4">
            <Text variant="body" weight="semibold">
              You're offline
            </Text>
            <Text variant="caption" color="secondary">
              We'll refresh your quotes automatically when you're back.
            </Text>
          </View>
        )}

        <Button testID="request-new-quote" title="Request a new quote" onPress={() => setRequesting(true)} />
      </ScrollView>
    </Screen>
  );
}
