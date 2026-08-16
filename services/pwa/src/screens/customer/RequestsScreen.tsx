import { useMemo, useState } from "react";
import { Pressable, ScrollView, TextInput, View } from "react-native";
import { useRouter } from "expo-router";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { IconButton } from "../../components/ui/IconButton";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { CustomerQuoteRequestFlow } from "./CustomerQuoteRequestFlow";
import { MOCK_QUOTES, getQuoteTotal } from "../../data/mockQuotes";
import { useBusiness } from "../../theme/ThemeProvider";
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
    background: "#EFF6FF",
    border: "#BFDBFE",
    text: "#1D4ED8",
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
  onBack,
  onComplete,
}: {
  quote: Quote;
  onBack: () => void;
  onComplete: () => void;
}) {
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [selectedTime, setSelectedTime] = useState<string | null>(null);
  const total = useMemo(() => getQuoteTotal(quote), [quote]);

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
            £{total.total.toFixed(2)}
          </Text>
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
                      backgroundColor: active ? "#EFF6FF" : "#F8FAFC",
                      borderColor: active ? "#2563EB" : "#E2E8F0",
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
                      backgroundColor: active ? "#EFF6FF" : "#F8FAFC",
                      borderColor: active ? "#2563EB" : "#E2E8F0",
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
          title="Confirm booking"
          onPress={onComplete}
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

      <ScrollView className="flex-1" contentContainerStyle={{ gap: 16, paddingBottom: 40 }}>
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
    </Screen>
  );
}

function CustomerQuoteView({
  quote,
  status,
  onBack,
  onAccept,
  onReject,
  onRequestChanges,
  onBook,
}: {
  quote: Quote;
  status: CustomerQuoteStatus;
  onBack: () => void;
  onAccept: () => void;
  onReject: () => void;
  onRequestChanges: () => void;
  onBook: () => void;
}) {
  const { business } = useBusiness();
  const totals = useMemo(() => getQuoteTotal(quote), [quote]);
  const isOpen = status === "open";
  const isAccepted = status === "accepted";
  const isRejected = status === "rejected";
  const isAwaiting = status === "awaiting_review";
  const isExpired = status === "expired";

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
              £{totals.subtotal.toFixed(2)}
            </Text>
          </View>
          <View className="flex-row items-center justify-between">
            <Text variant="caption" color="secondary">
              VAT ({(quote.vatRate * 100).toFixed(0)}%)
            </Text>
            <Text variant="caption" color="secondary">
              £{totals.vat.toFixed(2)}
            </Text>
          </View>
          <View className="flex-row items-center justify-between">
            <Text variant="body" weight="bold">
              Total
            </Text>
            <Text variant="title" weight="bold" color="primary">
              £{totals.total.toFixed(2)}
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
          {isOpen && (
            <>
              <Button title="Accept quote" onPress={onAccept} />
              <Button title="Reject quote" variant="outline" onPress={onReject} />
              <Button title="Request changes" variant="ghost" onPress={onRequestChanges} />
            </>
          )}

          {isAccepted && (
            <View className="gap-2 rounded-2xl border border-green-200 bg-green-50 p-4">
              <Text variant="body" weight="semibold" color="success">
                Quote accepted
              </Text>
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
              <Button title="Request a revised quote" variant="outline" onPress={() => {}} />
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
              <Button title="Request a revised quote" variant="outline" onPress={() => {}} />
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

export function RequestsScreen({ navigation }: RequestsScreenProps) {
  const { business } = useBusiness();
  const router = useRouter();

  const [requesting, setRequesting] = useState(false);
  const [view, setView] = useState<"list" | "detail" | "reject" | "booking">("list");
  const [selectedQuoteId, setSelectedQuoteId] = useState<string | null>(null);
  const [statusOverrides, setStatusOverrides] = useState<Record<string, QuoteStatus>>({});

  const effectiveStatus = (quote: Quote): CustomerQuoteStatus => {
    const status = statusOverrides[quote.id] ?? quote.status;
    return STATUS_MAP[status] ?? "open";
  };

  const selectedQuote = selectedQuoteId ? MOCK_QUOTES.find((q) => q.id === selectedQuoteId) : null;

  const openMessagesWithQuote = (quote: Quote) => {
    router.push({
      pathname: "/(customer)/messages",
      params: { quoteRef: `${quote.title} (${quote.id.toUpperCase()})` },
    });
  };

  if (requesting) {
    return <CustomerQuoteRequestFlow onClose={() => setRequesting(false)} />;
  }

  if (view === "detail" && selectedQuote) {
    return (
      <CustomerQuoteView
        quote={selectedQuote}
        status={effectiveStatus(selectedQuote)}
        onBack={() => setView("list")}
        onAccept={() => {
          setStatusOverrides((prev) => ({ ...prev, [selectedQuote.id]: "accepted" }));
          setView("booking");
        }}
        onReject={() => setView("reject")}
        onRequestChanges={() => openMessagesWithQuote(selectedQuote)}
        onBook={() => setView("booking")}
      />
    );
  }

  if (view === "reject" && selectedQuote) {
    return (
      <RejectQuoteView
        quote={selectedQuote}
        onBack={() => setView("detail")}
        onConfirm={(reason) => {
          console.log("Quote rejected:", selectedQuote.id, reason);
          setStatusOverrides((prev) => ({ ...prev, [selectedQuote.id]: "rejected" }));
          setView("detail");
        }}
      />
    );
  }

  if (view === "booking" && selectedQuote) {
    return (
      <BookDateView
        quote={selectedQuote}
        onBack={() => setView("detail")}
        onComplete={() => {
          setView("list");
          router.push("/(customer)/calendar");
        }}
      />
    );
  }

  return (
    <Screen>
      <Header
        title="My quotes"
        rightAction={
          <IconButton
            icon="profile"
            size={24}
            color="#374151"
            onPress={() => navigation.navigate("Profile")}
            accessibilityLabel="Profile"
          />
        }
      />

      <ScrollView className="flex-1" contentContainerStyle={{ gap: 16, paddingBottom: 40 }}>
        <Text variant="body" color="secondary">
          Track your quote requests and received quotes from {business?.name ?? "your electrician"}.
        </Text>

        {MOCK_QUOTES.map((quote) => {
          const status = effectiveStatus(quote);
          const isAwaiting = status === "awaiting_review";
          const total = isAwaiting ? null : getQuoteTotal(quote);

          return (
            <Pressable
              key={quote.id}
              onPress={() => {
                setSelectedQuoteId(quote.id);
                setView("detail");
              }}
              testID={`quote-card-${quote.id}`}
            >
              <View
                className="gap-2 rounded-2xl border p-4"
                style={{
                  backgroundColor: status === "open" ? "#EFF6FF" : "#FFFFFF",
                  borderColor: status === "open" ? "#BFDBFE" : "#E5E7EB",
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
                      £{total?.total.toFixed(2)}
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
        })}

        <Button title="Request a new quote" onPress={() => setRequesting(true)} />
      </ScrollView>
    </Screen>
  );
}
