import { useEffect, useMemo, useRef, useState } from "react";
import {
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  TextInput,
  View,
} from "react-native";
import DateTimePicker from "@react-native-community/datetimepicker";
import { useRouter } from "expo-router";
import { Button } from "../../components/ui/Button";
import { FormField } from "../../components/ui/FormField";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { useContactsList, findOrCreateContact } from "../../api/contacts";
import { useCreateJob, useConvertQuoteToJob, useScheduleSuggestion } from "../../api/jobs";
import type { MeasurementEntry, ScheduleSuggestion } from "../../api/jobs";
import { ApiQuote, fetchQuotes, setQuoteApproval, useApiQuote } from "../../api/quotes";
import { fetchAvailability, useAvailability } from "../../api/appointments";
import { useUsersList } from "../../api/users";
import { ApiError } from "../../lib/apiClient";
import { useQuery, useQueryClient } from "@tanstack/react-query";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const TIME_RE = /^\d{2}:\d{2}$/;
const HOUR_UNIT_RE = /^(h|hr|hrs|hour|hours)$/i;
// Stored accepted_dates entries: "YYYY-MM-DD" or "YYYY-MM-DD (morning)".
const PREFERENCE_RE = /^(\d{4}-\d{2}-\d{2})(?:\s*\(([^)]+)\))?$/;

const PREFERENCE_RANKS = ["1st choice", "2nd choice", "3rd choice"];

type QuoteDatePreference = { date: string; label: string; startTime: string | null };

/**
 * Parse one stored accepted_dates entry into a tappable date/time chip.
 * Null for the customer app's free-text labels ("Fri 12 Sep") — those stay
 * display-only. The coarse window maps to a start time (09:00 / 13:00),
 * matching the server-side draft-job convention.
 */
export function parseQuotePreference(entry: string): QuoteDatePreference | null {
  const match = PREFERENCE_RE.exec(entry.trim());
  if (!match) return null;
  const day = new Date(`${match[1]}T12:00:00`);
  if (Number.isNaN(day.getTime())) return null;
  const dateLabel = day.toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
  const window = match[2]?.trim().toLowerCase();
  const startTime = window === "morning" ? "09:00" : window === "afternoon" ? "13:00" : null;
  return { date: match[1], label: window ? `${dateLabel} · ${match[2]}` : dateLabel, startTime };
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

function toLocalIsoDate(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function toHHMM(d: Date): string {
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Sum labour-hour line items (3 lines × 10h → 30 working hours). */
export function quotedLabourHours(quote: ApiQuote): number {
  return (quote.lineItems ?? []).reduce((sum, li) => {
    if (!HOUR_UNIT_RE.test((li.unit ?? "").trim())) return sum;
    return sum + (parseFloat(li.quantity) || 0);
  }, 0);
}

/** Quote's duration estimate: server estimate first, labour-hours fallback. */
function quotedEstimatedHours(quote: ApiQuote): number {
  const server = parseFloat(quote.estimatedHours ?? "");
  if (!Number.isNaN(server) && server > 0) return server;
  return quotedLabourHours(quote);
}

/** "Tue 16 Sep (+ 2 more days)" label for a schedule suggestion. */
function suggestionLabel(suggestion: ScheduleSuggestion): string {
  const start = new Date(`${suggestion.startDate}T12:00:00`);
  const day = start.toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
  const extra = suggestion.days.length - 1;
  return extra > 0 ? `${day} (+ ${extra} more day${extra > 1 ? "s" : ""})` : day;
}

/** Earliest free 1-hour slot across the next 7 days (tomorrow first). */
async function suggestFirstSlot(): Promise<{ date: string; time: string } | null> {
  for (let offset = 1; offset <= 7; offset += 1) {
    const day = new Date();
    day.setDate(day.getDate() + offset);
    const iso = toLocalIsoDate(day);
    try {
      const slots = await fetchAvailability(iso);
      if (slots.length > 0) {
        return { date: iso, time: toHHMM(new Date(slots[0])) };
      }
    } catch {
      return null;
    }
  }
  return null;
}

/** "address · postcode" display line for a contact/quote customer. */
function contactAddressLine(contact: { address: string | null; postcode: string | null }): string {
  return [contact.address, contact.postcode].filter(Boolean).join(" · ");
}

export type JobCreateScreenProps = {
  onClose: () => void;
  /** Preselect this quote (e.g. from the quote screen's "Convert to…" sheet). */
  initialQuoteId?: string;
};

/** Manual or quote-prefilled job entry with scheduling, duration and assignee. */
export function JobCreateScreen({ onClose, initialQuoteId }: JobCreateScreenProps) {
  const router = useRouter();
  const { contacts, isLoading: contactsLoading } = useContactsList();
  const { users } = useUsersList();
  const createJob = useCreateJob();
  const convertToJob = useConvertQuoteToJob();
  const queryClient = useQueryClient();

  const quotesQuery = useQuery({ queryKey: ["quotes"], queryFn: fetchQuotes });
  // Approved quotes convert directly; sent quotes are marked accepted during
  // conversion (customer agreed off-app — the trade app has no other approve
  // path). Draft/rejected/invoiced quotes stay excluded, as the server does.
  const convertibleQuotes = useMemo(
    () =>
      (quotesQuery.data ?? []).filter((q) => q.status === "approved" || q.status === "sent"),
    [quotesQuery.data]
  );

  const [title, setTitle] = useState("");
  const [selectedQuoteId, setSelectedQuoteId] = useState<string | null>(initialQuoteId ?? null);
  const [quoteSearch, setQuoteSearch] = useState("");
  const [customerMode, setCustomerMode] = useState<"search" | "new">("search");
  const [customerSearch, setCustomerSearch] = useState("");
  const [contactId, setContactId] = useState<string | null>(null);
  const [newCustomerName, setNewCustomerName] = useState("");
  const [newCustomerPhone, setNewCustomerPhone] = useState("");
  const [newCustomerEmail, setNewCustomerEmail] = useState("");
  const [newCustomerPostcode, setNewCustomerPostcode] = useState("");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [durationHours, setDurationHours] = useState("");
  const [assignedUserId, setAssignedUserId] = useState<string | null>(null);
  const [measurements, setMeasurements] = useState<MeasurementEntry[]>([]);
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [showDatePicker, setShowDatePicker] = useState(false);
  const [showTimePicker, setShowTimePicker] = useState(false);
  const [pendingDate, setPendingDate] = useState<Date>(new Date());

  // A quoteId in the route (Convert-to flow) locks the quote attribution —
  // no quote search and no deselect in that mode.
  const quoteLocked = initialQuoteId != null;

  // The locked quote is fetched directly by id — never resolved from the
  // sent/approved-filtered list, which would hang the banner forever for
  // drafts or after a slow/failed list fetch.
  const lockedQuoteQuery = useApiQuote(quoteLocked ? initialQuoteId : undefined);
  const lockedQuoteConvertible =
    lockedQuoteQuery.quote != null &&
    (lockedQuoteQuery.quote.status === "approved" || lockedQuoteQuery.quote.status === "sent");

  const selectedQuote = useMemo(() => {
    if (quoteLocked) {
      return lockedQuoteConvertible ? lockedQuoteQuery.quote ?? null : null;
    }
    return convertibleQuotes.find((q) => q.id === selectedQuoteId) ?? null;
  }, [quoteLocked, lockedQuoteConvertible, lockedQuoteQuery.quote, convertibleQuotes, selectedQuoteId]);

  const quoteMatches = useMemo(() => {
    const needle = quoteSearch.trim().toLowerCase();
    if (!needle) return [];
    return convertibleQuotes.filter((q) =>
      [q.title, q.customer.name].join(" ").toLowerCase().includes(needle)
    );
  }, [convertibleQuotes, quoteSearch]);

  const selectedContact = useMemo(
    () => contacts.find((c) => c.id === contactId) ?? null,
    [contacts, contactId]
  );

  const customerMatches = useMemo(() => {
    const needle = customerSearch.trim().toLowerCase();
    if (!needle) return [];
    return contacts.filter((c) =>
      [c.name, c.phone ?? "", c.email ?? ""].join(" ").toLowerCase().includes(needle)
    );
  }, [contacts, customerSearch]);

  // N18: selecting a quote prefills title, customer, duration (from the
  // quote's server-side estimated hours, falling back to quoted labour hours)
  // and proposes the customer's 1st-choice date when they picked one at
  // acceptance (falling back to the earliest available start slot).
  const prefilledQuoteRef = useRef<string | null>(null);
  useEffect(() => {
    if (!selectedQuote || prefilledQuoteRef.current === selectedQuote.id) return;
    prefilledQuoteRef.current = selectedQuote.id;
    setTitle(selectedQuote.title);
    setContactId(selectedQuote.customer.id);
    setCustomerMode("search");
    const hours = quotedEstimatedHours(selectedQuote);
    setDurationHours(hours > 0 ? String(hours) : "");
    const firstChoice = (selectedQuote.acceptedDates ?? [])
      .map(parseQuotePreference)
      .find((p): p is QuoteDatePreference => p !== null);
    if (firstChoice) {
      setDate(firstChoice.date);
      if (firstChoice.startTime) {
        setTime(firstChoice.startTime);
      } else {
        void fetchAvailability(firstChoice.date)
          .then((slots) => {
            if (slots.length > 0) setTime(toHHMM(new Date(slots[0])));
          })
          .catch(() => {});
      }
      return;
    }
    void suggestFirstSlot().then((slot) => {
      if (slot) {
        setDate(slot.date);
        setTime(slot.time);
      }
    });
  }, [selectedQuote]);

  // The customer's ranked preferences from quote acceptance — tappable so
  // the electrician lands on the 2nd/3rd choice when the 1st doesn't fit.
  const quotePreferences = useMemo(
    () =>
      (selectedQuote?.acceptedDates ?? []).map((entry) => ({
        entry,
        parsed: parseQuotePreference(entry),
      })),
    [selectedQuote]
  );

  const applyPreference = (parsed: QuoteDatePreference) => {
    setDate(parsed.date);
    if (parsed.startTime) {
      setTime(parsed.startTime);
      return;
    }
    void fetchAvailability(parsed.date)
      .then((slots) => {
        if (slots.length > 0) setTime(toHHMM(new Date(slots[0])));
      })
      .catch(() => {});
  };

  // Server-side recommendation: earliest start where the quote's whole
  // working-day block sequence fits around the existing calendar.
  const { suggestion: scheduleSuggestion } = useScheduleSuggestion(selectedQuote?.id ?? null);
  const isMultiDayQuote = selectedQuote?.isMultiDay === true;

  const dateValid = date.trim() === "" || DATE_RE.test(date.trim());
  const timeValid = time.trim() === "" || TIME_RE.test(time.trim());
  const durationValid =
    durationHours.trim() === "" || (!Number.isNaN(parseFloat(durationHours)) && parseFloat(durationHours) > 0);

  const { slots: availableSlots, isLoading: availabilityLoading } = useAvailability(
    DATE_RE.test(date.trim()) ? date.trim() : null
  );
  const suggestedSlot = availableSlots[0] ?? null;

  const openPicker = (kind: "date" | "time") => {
    const base =
      kind === "date" && DATE_RE.test(date.trim())
        ? new Date(`${date.trim()}T12:00:00`)
        : kind === "time" && TIME_RE.test(time.trim())
          ? new Date(`2000-01-01T${time.trim()}:00`)
          : new Date();
    setPendingDate(base);
    if (kind === "date") setShowDatePicker(true);
    else setShowTimePicker(true);
  };

  // Spinner pickers fire on every drum tick — stage and commit on Done.
  const onPickerValueChange = (_event: unknown, selected?: Date) => {
    if (selected) setPendingDate(selected);
  };

  const confirmPicker = (kind: "date" | "time") => {
    if (kind === "date") {
      setDate(toLocalIsoDate(pendingDate));
      setShowDatePicker(false);
    } else {
      setTime(toHHMM(pendingDate));
      setShowTimePicker(false);
    }
  };

  const resolveSchedule = (): { start?: string; end?: string } | string => {
    if (date.trim() === "" && time.trim() === "") return {};
    if (!DATE_RE.test(date.trim()) || !TIME_RE.test(time.trim())) {
      return "Enter both a date (YYYY-MM-DD) and a start time (HH:MM).";
    }
    const start = new Date(`${date.trim()}T${time.trim()}:00`);
    if (Number.isNaN(start.getTime())) return "That date/time isn't valid.";
    let end: Date | undefined;
    if (durationHours.trim() !== "") {
      const hours = parseFloat(durationHours);
      if (Number.isNaN(hours) || hours <= 0) return "Duration must be a positive number of hours.";
      end = new Date(start.getTime() + hours * 60 * 60 * 1000);
    }
    return { start: start.toISOString(), end: end?.toISOString() };
  };

  // Blank rows are dropped rather than rejected — the API requires a non-empty
  // label and value on every stored entry.
  const cleanedMeasurements = () =>
    measurements
      .map((entry) => ({ label: entry.label.trim(), value: entry.value.trim() }))
      .filter((entry) => entry.label !== "" && entry.value !== "");

  const handleCreate = async () => {
    setError(null);
    if (!selectedQuote && !title.trim()) {
      setError("Enter a job title.");
      return;
    }
    const schedule = resolveSchedule();
    if (typeof schedule === "string") {
      setError(schedule);
      return;
    }
    const recordedMeasurements = cleanedMeasurements();

    let resolvedContactId = contactId;
    if (selectedQuote) {
      resolvedContactId = selectedQuote.customer.id;
    } else if (customerMode === "new") {
      if (!newCustomerName.trim()) {
        setError("Enter the new customer's name.");
        return;
      }
      try {
        const contact = await findOrCreateContact({
          name: newCustomerName.trim(),
          phone: newCustomerPhone.trim() || null,
          email: newCustomerEmail.trim() || null,
          postcode: newCustomerPostcode.trim() || null,
        });
        resolvedContactId = contact.id;
      } catch (err) {
        setError(
          err instanceof ApiError ? err.detail : "Couldn't create the customer. Please try again."
        );
        return;
      }
    }
    if (!resolvedContactId) {
      setError("Pick a customer.");
      return;
    }

    setSubmitting(true);
    try {
      let job;
      if (selectedQuote) {
        if (selectedQuote.status !== "approved") {
          // Customer agreed off-app: mark the quote accepted first so the
          // server's approved-only conversion rule passes.
          await setQuoteApproval(selectedQuote.id, true);
          queryClient.invalidateQueries({ queryKey: ["quotes"] });
          queryClient.invalidateQueries({ queryKey: ["quote", selectedQuote.id] });
        }
        job = await convertToJob.mutateAsync({
          quoteId: selectedQuote.id,
          schedule: {
            scheduledStart: schedule.start,
            scheduledEnd: schedule.end,
            notes: notes.trim() !== "" ? notes.trim() : undefined,
            measurements:
              recordedMeasurements.length > 0 ? recordedMeasurements : undefined,
            assignedUserId: assignedUserId ?? undefined,
          },
        });
      } else {
        job = await createJob.mutateAsync({
          contactId: resolvedContactId,
          title: title.trim(),
          scheduledStart: schedule.start,
          scheduledEnd: schedule.end,
          notes: notes.trim() !== "" ? notes.trim() : undefined,
          measurements: recordedMeasurements.length > 0 ? recordedMeasurements : undefined,
          assignedUserId: assignedUserId ?? undefined,
        });
      }
      router.replace(`/(trade)/job/${job.id}`);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail : "Couldn't create the job. Please try again."
      );
    } finally {
      setSubmitting(false);
    }
  };

  const busy = submitting || createJob.isPending || convertToJob.isPending;
  // A locked (route-pinned) quote that failed to load or isn't convertible
  // blocks creation — the error panel above is the way out.
  const createDisabled = busy || (quoteLocked && !selectedQuote);

  return (
    <Screen>
      <Header testID="job-create-back" title="New job" onBack={onClose} />

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView
          className="flex-1"
          style={{ minHeight: 0 }}
          contentContainerClassName="gap-3 pb-4"
          keyboardShouldPersistTaps="handled"
        >
          {quoteLocked ? (
            lockedQuoteQuery.isError ||
            (lockedQuoteQuery.quote != null && !lockedQuoteConvertible) ? (
              <View className="gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3">
                <Text testID="job-create-quote-error" variant="body" weight="semibold">
                  {lockedQuoteQuery.isError
                    ? "Couldn't load this quote."
                    : `This quote can't be converted — it's ${lockedQuoteQuery.quote?.status}.`}
                </Text>
                <Text variant="caption" color="secondary">
                  {lockedQuoteQuery.isError
                    ? "Check your connection and try again, or go back and pick another quote."
                    : "Only sent or accepted quotes can become jobs."}
                </Text>
                <View className="flex-row gap-2">
                  {lockedQuoteQuery.isError && (
                    <Button
                      testID="job-create-quote-retry"
                      title="Retry"
                      size="sm"
                      variant="outline"
                      onPress={() => void lockedQuoteQuery.refetch()}
                    />
                  )}
                  <Button
                    testID="job-create-quote-error-back"
                    title="Back"
                    size="sm"
                    variant="outline"
                    onPress={onClose}
                  />
                </View>
              </View>
            ) : (
            <View
              testID="job-create-quote-locked"
              className="gap-1 rounded-xl border border-primary bg-primary-50 p-3"
            >
              {selectedQuote ? (
                <>
                  <Text variant="body" weight="semibold">
                    From quote: {selectedQuote.title}
                  </Text>
                  <Text variant="caption" color="secondary">
                    {selectedQuote.status === "approved" ? "Accepted" : "Sent"} · this job stays
                    linked to the quote it was converted from.
                  </Text>
                  {selectedQuote.status !== "approved" && (
                    <Text testID="job-create-quote-mark-accepted" variant="caption" color="secondary">
                      Will be marked as accepted when the job is created.
                    </Text>
                  )}
                </>
              ) : (
                <Text variant="caption" color="secondary">
                  Loading the quote…
                </Text>
              )}
            </View>
            )
          ) : (
            convertibleQuotes.length > 0 && (
              <View className="gap-2">
                <Text variant="body" weight="semibold">
                  From a quote
                </Text>
                <Text variant="caption" color="secondary">
                  Optional — prefills the customer, duration and a suggested start slot.
                </Text>
                {selectedQuote ? (
                  <View
                    testID="job-create-quote-selected"
                    className="gap-1 rounded-xl border border-primary bg-primary-50 p-3"
                  >
                    <View className="flex-row items-start justify-between gap-2">
                      <View className="flex-1">
                        <Text variant="body" weight="semibold">
                          {selectedQuote.title}
                        </Text>
                        <Text variant="caption" color="secondary">
                          {selectedQuote.customer.name} ·{" "}
                          {selectedQuote.status === "approved" ? "Accepted" : "Sent"}
                        </Text>
                      </View>
                      <Pressable
                        testID="job-create-quote-clear"
                        accessibilityLabel="Clear quote"
                        onPress={() => setSelectedQuoteId(null)}
                      >
                        <Text variant="body" weight="semibold" color="primary">
                          ✕
                        </Text>
                      </Pressable>
                    </View>
                    {selectedQuote.status !== "approved" && (
                      <Text testID="job-create-quote-mark-accepted" variant="caption" color="secondary">
                        Will be marked as accepted when the job is created.
                      </Text>
                    )}
                  </View>
                ) : (
                  <>
                    <TextInput
                      testID="job-create-quote-search"
                      className="h-12 rounded-xl border border-slate-200 bg-white px-4 text-base text-slate-900"
                      value={quoteSearch}
                      onChangeText={setQuoteSearch}
                      placeholder="Search quotes by customer or title"
                      placeholderTextColor="#94A3B8"
                      autoCapitalize="none"
                      autoCorrect={false}
                    />
                    {quoteSearch.trim() === "" ? (
                      <Text
                        testID="job-create-quote-search-hint"
                        variant="caption"
                        color="secondary"
                      >
                        Search by customer or quote title.
                      </Text>
                    ) : quoteMatches.length === 0 ? (
                      <Text testID="job-create-no-quote-matches" variant="caption" color="secondary">
                        No quotes match your search.
                      </Text>
                    ) : (
                      quoteMatches.map((quote) => (
                        <Pressable
                          key={quote.id}
                          testID={`job-create-quote-option-${quote.id}`}
                          onPress={() => {
                            setSelectedQuoteId(quote.id);
                            setQuoteSearch("");
                          }}
                        >
                          <View className="rounded-xl border border-slate-200 bg-white p-3">
                            <Text variant="body">{quote.title}</Text>
                            <Text variant="caption" color="secondary">
                              {quote.customer.name} ·{" "}
                              {quote.status === "approved" ? "Accepted" : "Sent"}
                            </Text>
                          </View>
                        </Pressable>
                      ))
                    )}
                  </>
                )}
              </View>
            )
          )}

          <FormField
            testID="job-create-title"
            label="Title"
            value={title}
            onChangeText={setTitle}
            placeholder="e.g. Fuse board replacement"
          />

          <View className="gap-2">
            <Text variant="body" weight="semibold">
              Customer
            </Text>
            {selectedQuote ? (
              <View className="gap-0.5">
                <Text testID="job-create-quote-customer" variant="caption" color="secondary">
                  {selectedQuote.customer.name} — from the selected quote.
                </Text>
                {contactAddressLine(selectedQuote.customer) !== "" && (
                  <Text testID="job-create-quote-address" variant="caption" color="secondary">
                    {contactAddressLine(selectedQuote.customer)}
                  </Text>
                )}
              </View>
            ) : customerMode === "new" ? (
              <View className="gap-2">
                <Pressable
                  testID="job-create-customer-existing"
                  onPress={() => setCustomerMode("search")}
                >
                  <Text variant="caption" weight="semibold" color="primary">
                    ‹ Search existing customers
                  </Text>
                </Pressable>
                <View className="gap-2 rounded-xl border border-slate-200 bg-white p-3">
                  <FormField
                    testID="job-create-new-customer-name"
                    label="Name"
                    value={newCustomerName}
                    onChangeText={setNewCustomerName}
                    placeholder="e.g. Jane Smith"
                  />
                  <FormField
                    testID="job-create-new-customer-phone"
                    label="Phone"
                    value={newCustomerPhone}
                    onChangeText={setNewCustomerPhone}
                    placeholder="Optional"
                    keyboardType="phone-pad"
                  />
                  <FormField
                    testID="job-create-new-customer-email"
                    label="Email"
                    value={newCustomerEmail}
                    onChangeText={setNewCustomerEmail}
                    placeholder="Optional"
                    autoCapitalize="none"
                    keyboardType="email-address"
                  />
                  <FormField
                    testID="job-create-new-customer-postcode"
                    label="Postcode"
                    value={newCustomerPostcode}
                    onChangeText={setNewCustomerPostcode}
                    placeholder="Optional"
                    autoCapitalize="characters"
                  />
                </View>
              </View>
            ) : contactId && selectedContact ? (
              <View
                testID="job-create-contact-selected"
                className="flex-row items-center justify-between gap-2 rounded-xl border border-primary bg-primary-50 p-3"
              >
                <View className="flex-1">
                  <Text variant="body" weight="semibold">
                    {selectedContact.name}
                  </Text>
                  {selectedContact.postcode ? (
                    <Text variant="caption" color="secondary">
                      {selectedContact.postcode}
                    </Text>
                  ) : null}
                </View>
                <Pressable
                  testID="job-create-contact-clear"
                  accessibilityLabel="Clear customer"
                  onPress={() => setContactId(null)}
                >
                  <Text variant="body" weight="semibold" color="primary">
                    ✕
                  </Text>
                </Pressable>
              </View>
            ) : (
              <View className="gap-2">
                <TextInput
                  testID="job-create-customer-search"
                  className="h-12 rounded-xl border border-slate-200 bg-white px-4 text-base text-slate-900"
                  value={customerSearch}
                  onChangeText={setCustomerSearch}
                  placeholder="Search customers by name, phone or email"
                  placeholderTextColor="#94A3B8"
                  autoCapitalize="none"
                  autoCorrect={false}
                />
                {contactsLoading ? (
                  <Text variant="caption" color="secondary">
                    Loading customers…
                  </Text>
                ) : (
                  <>
                    {customerSearch.trim() === "" ? (
                      <Text
                        testID="job-create-customer-search-hint"
                        variant="caption"
                        color="secondary"
                      >
                        Search by name, phone or email
                      </Text>
                    ) : customerMatches.length === 0 ? (
                      <Text testID="job-create-no-contacts" variant="caption" color="secondary">
                        {contacts.length === 0
                          ? "No customers yet — add one below."
                          : "No customers match your search."}
                      </Text>
                    ) : (
                      customerMatches.map((contact) => (
                        <Pressable
                          key={contact.id}
                          testID={`job-create-contact-option-${contact.id}`}
                          onPress={() => {
                            setContactId(contact.id);
                            setCustomerSearch("");
                          }}
                        >
                          <View className="rounded-xl border border-slate-200 bg-white p-3">
                            <Text variant="body">{contact.name}</Text>
                            {contact.postcode ? (
                              <Text variant="caption" color="secondary">
                                {contact.postcode}
                              </Text>
                            ) : null}
                          </View>
                        </Pressable>
                      ))
                    )}
                    <Pressable
                      testID="job-create-customer-new"
                      onPress={() => setCustomerMode("new")}
                    >
                      <View className="rounded-xl border border-dashed border-slate-300 bg-white p-3">
                        <Text variant="body" weight="semibold" color="primary">
                          + Add new customer
                        </Text>
                      </View>
                    </Pressable>
                  </>
                )}
              </View>
            )}
          </View>

          {isMultiDayQuote && (
            <View
              testID="job-create-multiday"
              className="gap-1 rounded-xl border border-amber-200 bg-amber-50 p-3"
            >
              <Text variant="body" weight="semibold">
                Multi-day job
                {scheduleSuggestion ? ` — spans ${scheduleSuggestion.days.length} working days` : ""}
              </Text>
              <Text variant="caption" color="secondary">
                The schedule is split across consecutive working days, capped at your daily working
                hours.
              </Text>
            </View>
          )}

          {scheduleSuggestion && (
            <Pressable
              testID="job-create-schedule-suggestion"
              onPress={() => {
                setDate(scheduleSuggestion.startDate);
                setTime(scheduleSuggestion.startTime);
              }}
            >
              <View className="rounded-xl border border-primary-100 bg-primary-50 p-3">
                <Text variant="caption" color="secondary">
                  Earliest fit: {suggestionLabel(scheduleSuggestion)} — tap to use it.
                </Text>
              </View>
            </Pressable>
          )}

          {selectedQuote && quotePreferences.length > 0 && (
            <View className="gap-2">
              <Text variant="body" weight="semibold">
                Customer's preferred dates
              </Text>
              <Text variant="caption" color="secondary">
                Chosen when the quote was accepted — tap one to schedule it, or pick another
                date below.
              </Text>
              <View className="flex-row flex-wrap gap-2">
                {quotePreferences.map(({ entry, parsed }, index) =>
                  parsed ? (
                    <Pressable
                      key={entry}
                      testID={`job-create-preference-${index}`}
                      onPress={() => applyPreference(parsed)}
                    >
                      <View
                        className={`rounded-xl border p-3 ${
                          date === parsed.date
                            ? "border-primary bg-primary-50"
                            : "border-slate-200 bg-white"
                        }`}
                      >
                        <Text variant="caption" color="secondary">
                          {PREFERENCE_RANKS[index] ?? `Choice ${index + 1}`}
                        </Text>
                        <Text variant="body" weight="semibold">
                          {parsed.label}
                        </Text>
                      </View>
                    </Pressable>
                  ) : (
                    <View
                      key={entry}
                      testID={`job-create-preference-${index}`}
                      className="rounded-xl border border-slate-200 bg-white p-3"
                    >
                      <Text variant="caption" color="secondary">
                        {PREFERENCE_RANKS[index] ?? `Choice ${index + 1}`}
                      </Text>
                      <Text variant="body">{entry}</Text>
                    </View>
                  )
                )}
              </View>
            </View>
          )}

          {Platform.OS === "web" ? (
            <>
              <FormField
                testID="job-create-date"
                label="Date"
                value={date}
                onChangeText={setDate}
                placeholder="YYYY-MM-DD"
                helper="Optional — leave blank to schedule later."
                error={dateValid ? null : "Use YYYY-MM-DD, e.g. 2026-09-12"}
                autoCapitalize="none"
                maxLength={10}
              />
              <FormField
                testID="job-create-time"
                label="Start time"
                value={time}
                onChangeText={setTime}
                placeholder="HH:MM"
                error={timeValid ? null : "Use HH:MM, e.g. 09:00"}
                autoCapitalize="none"
                maxLength={5}
              />
            </>
          ) : (
            <View className="flex-row gap-2">
              <View className="flex-1 gap-1">
                <Text variant="body" weight="semibold">
                  Date
                </Text>
                <Pressable testID="job-create-date" onPress={() => openPicker("date")}>
                  <View className="rounded-xl border border-slate-200 bg-white px-4 py-3">
                    <Text variant="body" color={date ? undefined : "secondary"}>
                      {date || "Pick a date"}
                    </Text>
                  </View>
                </Pressable>
              </View>
              <View className="flex-1 gap-1">
                <Text variant="body" weight="semibold">
                  Start time
                </Text>
                <Pressable testID="job-create-time" onPress={() => openPicker("time")}>
                  <View className="rounded-xl border border-slate-200 bg-white px-4 py-3">
                    <Text variant="body" color={time ? undefined : "secondary"}>
                      {time || "Pick a time"}
                    </Text>
                  </View>
                </Pressable>
              </View>
            </View>
          )}

          {!scheduleSuggestion && DATE_RE.test(date.trim()) && (
            <View className="gap-1">
              {availabilityLoading ? (
                <Text variant="caption" color="secondary">
                  Checking your calendar…
                </Text>
              ) : suggestedSlot ? (
                <Pressable
                  testID="job-create-suggested-slot"
                  onPress={() => setTime(toHHMM(new Date(suggestedSlot)))}
                >
                  <View className="rounded-xl border border-primary-100 bg-primary-50 p-3">
                    <Text variant="caption" color="secondary">
                      First free slot that day: {toHHMM(new Date(suggestedSlot))} — tap to use it.
                    </Text>
                  </View>
                </Pressable>
              ) : (
                <Text testID="job-create-no-slots" variant="caption" color="secondary">
                  No free slots that day — your calendar is fully booked.
                </Text>
              )}
            </View>
          )}

          <FormField
            testID="job-create-duration"
            label="Duration (working hours)"
            value={durationHours}
            onChangeText={setDurationHours}
            placeholder="e.g. 30"
            helper={
              isMultiDayQuote
                ? "Total hours — split across consecutive working days when the job is created."
                : selectedQuote
                  ? "Prefilled from the quote's estimated hours — edit if the plan changed."
                  : "Optional — sets the job's end time from the start."
            }
            error={durationValid ? null : "Enter a positive number of hours, e.g. 8"}
            keyboardType="decimal-pad"
          />

          {/* Team gating: with a single active user (every sole_trader tenant)
              there is nothing to pick — the API auto-assigns that user, so the
              picker only renders once the tenant actually has staff to choose. */}
          {users.length > 1 && (
            <View className="gap-2">
              <Text variant="body" weight="semibold">
                Assigned to
              </Text>
              <View className="flex-row flex-wrap gap-2">
                <Button
                  testID="job-create-assignee-none"
                  title="Unassigned"
                  size="sm"
                  variant={assignedUserId === null ? "primary" : "outline"}
                  onPress={() => setAssignedUserId(null)}
                />
                {users.map((user) => (
                  <Button
                    key={user.id}
                    testID={`job-create-assignee-${user.id}`}
                    title={user.fullName}
                    size="sm"
                    variant={assignedUserId === user.id ? "primary" : "outline"}
                    onPress={() => setAssignedUserId(user.id)}
                  />
                ))}
              </View>
            </View>
          )}

          <View className="gap-2">
            <Text variant="body" weight="semibold">
              Measurements
            </Text>
            <Text variant="caption" color="secondary">
              Optional — e.g. cable run lengths, board height, room dimensions.
            </Text>
            {measurements.map((entry, index) => (
              <View key={index} className="flex-row items-center gap-2">
                <TextInput
                  testID={`job-create-measurement-label-${index}`}
                  className="h-12 flex-1 rounded-xl border border-slate-200 bg-white px-4 text-base text-slate-900"
                  value={entry.label}
                  onChangeText={(value) =>
                    setMeasurements((prev) =>
                      prev.map((e, i) => (i === index ? { ...e, label: value } : e))
                    )
                  }
                  placeholder="Label (e.g. Cable run)"
                  placeholderTextColor="#94A3B8"
                />
                <TextInput
                  testID={`job-create-measurement-value-${index}`}
                  className="h-12 flex-1 rounded-xl border border-slate-200 bg-white px-4 text-base text-slate-900"
                  value={entry.value}
                  onChangeText={(value) =>
                    setMeasurements((prev) =>
                      prev.map((e, i) => (i === index ? { ...e, value } : e))
                    )
                  }
                  placeholder="Value (e.g. 12 m)"
                  placeholderTextColor="#94A3B8"
                />
                <Pressable
                  testID={`job-create-measurement-remove-${index}`}
                  accessibilityLabel={`Remove measurement ${index + 1}`}
                  onPress={() => setMeasurements((prev) => prev.filter((_, i) => i !== index))}
                >
                  <Text variant="body" weight="semibold" color="primary">
                    ✕
                  </Text>
                </Pressable>
              </View>
            ))}
            <Button
              testID="job-create-measurement-add"
              title="+ Add measurement"
              variant="outline"
              size="sm"
              onPress={() => setMeasurements((prev) => [...prev, { label: "", value: "" }])}
            />
          </View>

          <FormField
            testID="job-create-notes"
            label="Notes"
            value={notes}
            onChangeText={setNotes}
            placeholder="Access details, parking, customer requests…"
            multiline
          />

          {error && (
            <View className="rounded-2xl bg-amber-50 p-3">
              <Text testID="job-create-error" variant="caption" color="warning">
                {error}
              </Text>
            </View>
          )}
        </ScrollView>

        <View className="border-t border-slate-200 bg-white pt-3 pb-2">
          <Button
            testID="job-create-submit"
            title={busy ? "Creating…" : "Create job"}
            disabled={createDisabled}
            onPress={() => void handleCreate()}
          />
        </View>
      </KeyboardAvoidingView>

      <Modal
        visible={showDatePicker}
        transparent
        animationType="slide"
        onRequestClose={() => setShowDatePicker(false)}
      >
        <Pressable className="flex-1 justify-end bg-black/40" onPress={() => setShowDatePicker(false)}>
          <Pressable className="rounded-t-3xl bg-white pb-8" onPress={() => {}}>
            <View className="flex-row items-center justify-between px-4 py-3">
              <Text variant="body" weight="semibold">
                Job date
              </Text>
              <Pressable testID="job-create-date-done" onPress={() => confirmPicker("date")}>
                <Text variant="body" weight="semibold" color="primary">
                  Done
                </Text>
              </Pressable>
            </View>
            <DateTimePicker
              value={pendingDate}
              mode="date"
              display="spinner"
              onChange={onPickerValueChange}
            />
          </Pressable>
        </Pressable>
      </Modal>

      <Modal
        visible={showTimePicker}
        transparent
        animationType="slide"
        onRequestClose={() => setShowTimePicker(false)}
      >
        <Pressable className="flex-1 justify-end bg-black/40" onPress={() => setShowTimePicker(false)}>
          <Pressable className="rounded-t-3xl bg-white pb-8" onPress={() => {}}>
            <View className="flex-row items-center justify-between px-4 py-3">
              <Text variant="body" weight="semibold">
                Start time
              </Text>
              <Pressable testID="job-create-time-done" onPress={() => confirmPicker("time")}>
                <Text variant="body" weight="semibold" color="primary">
                  Done
                </Text>
              </Pressable>
            </View>
            <DateTimePicker
              value={pendingDate}
              mode="time"
              display="spinner"
              onChange={onPickerValueChange}
            />
          </Pressable>
        </Pressable>
      </Modal>
    </Screen>
  );
}
