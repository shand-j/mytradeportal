import { useEffect, useMemo, useRef, useState } from "react";
import {
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
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
import { useCreateJob, useConvertQuoteToJob } from "../../api/jobs";
import { ApiQuote, fetchQuotes } from "../../api/quotes";
import { fetchAvailability, useAvailability } from "../../api/appointments";
import { useUsersList } from "../../api/users";
import { ApiError } from "../../lib/apiClient";
import { useQuery } from "@tanstack/react-query";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const TIME_RE = /^\d{2}:\d{2}$/;
const HOUR_UNIT_RE = /^(h|hr|hrs|hour|hours)$/i;

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

  const quotesQuery = useQuery({ queryKey: ["quotes"], queryFn: fetchQuotes });
  // Only approved quotes can convert to a job (server enforces it too).
  const convertibleQuotes = useMemo(
    () => (quotesQuery.data ?? []).filter((q) => q.status === "approved"),
    [quotesQuery.data]
  );

  const [title, setTitle] = useState("");
  const [selectedQuoteId, setSelectedQuoteId] = useState<string | null>(initialQuoteId ?? null);
  const [customerMode, setCustomerMode] = useState<"existing" | "new">("existing");
  const [contactId, setContactId] = useState<string | null>(null);
  const [newCustomerName, setNewCustomerName] = useState("");
  const [newCustomerPhone, setNewCustomerPhone] = useState("");
  const [newCustomerEmail, setNewCustomerEmail] = useState("");
  const [newCustomerPostcode, setNewCustomerPostcode] = useState("");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [durationHours, setDurationHours] = useState("");
  const [assignedUserId, setAssignedUserId] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [showDatePicker, setShowDatePicker] = useState(false);
  const [showTimePicker, setShowTimePicker] = useState(false);
  const [pendingDate, setPendingDate] = useState<Date>(new Date());

  const selectedQuote = useMemo(
    () => convertibleQuotes.find((q) => q.id === selectedQuoteId) ?? null,
    [convertibleQuotes, selectedQuoteId]
  );

  // N18: selecting a quote prefills title, customer, duration (from quoted
  // labour hours) and proposes the earliest available start slot.
  const prefilledQuoteRef = useRef<string | null>(null);
  useEffect(() => {
    if (!selectedQuote || prefilledQuoteRef.current === selectedQuote.id) return;
    prefilledQuoteRef.current = selectedQuote.id;
    setTitle(selectedQuote.title);
    setContactId(selectedQuote.customer.id);
    setCustomerMode("existing");
    const hours = quotedLabourHours(selectedQuote);
    setDurationHours(hours > 0 ? String(hours) : "");
    void suggestFirstSlot().then((slot) => {
      if (slot) {
        setDate(slot.date);
        setTime(slot.time);
      }
    });
  }, [selectedQuote]);

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
      const job = selectedQuote
        ? await convertToJob.mutateAsync({
            quoteId: selectedQuote.id,
            schedule: {
              scheduledStart: schedule.start,
              scheduledEnd: schedule.end,
              notes: notes.trim() !== "" ? notes.trim() : undefined,
              assignedUserId: assignedUserId ?? undefined,
            },
          })
        : await createJob.mutateAsync({
            contactId: resolvedContactId,
            title: title.trim(),
            scheduledStart: schedule.start,
            scheduledEnd: schedule.end,
            notes: notes.trim() !== "" ? notes.trim() : undefined,
            assignedUserId: assignedUserId ?? undefined,
          });
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
          {convertibleQuotes.length > 0 && (
            <View className="gap-2">
              <Text variant="body" weight="semibold">
                From an accepted quote
              </Text>
              <Text variant="caption" color="secondary">
                Optional — prefills the customer, duration and a suggested start slot.
              </Text>
              {convertibleQuotes.map((quote) => {
                const selected = quote.id === selectedQuoteId;
                return (
                  <Pressable
                    key={quote.id}
                    testID={`job-create-quote-${quote.id}`}
                    onPress={() => setSelectedQuoteId(selected ? null : quote.id)}
                  >
                    <View
                      className={`rounded-xl border p-3 ${
                        selected ? "border-blue-500 bg-blue-50" : "border-slate-200 bg-white"
                      }`}
                    >
                      <Text variant="body" weight={selected ? "semibold" : "normal"}>
                        {quote.title}
                      </Text>
                      <Text variant="caption" color="secondary">
                        {quote.customer.name}
                      </Text>
                    </View>
                  </Pressable>
                );
              })}
            </View>
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
              <Text testID="job-create-quote-customer" variant="caption" color="secondary">
                {selectedQuote.customer.name} — from the selected quote.
              </Text>
            ) : (
              <>
                <View className="flex-row gap-2">
                  <Button
                    testID="job-create-customer-existing"
                    title="Existing"
                    size="sm"
                    variant={customerMode === "existing" ? "primary" : "outline"}
                    onPress={() => setCustomerMode("existing")}
                  />
                  <Button
                    testID="job-create-customer-new"
                    title="New customer"
                    size="sm"
                    variant={customerMode === "new" ? "primary" : "outline"}
                    onPress={() => setCustomerMode("new")}
                  />
                </View>
                {customerMode === "new" ? (
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
                ) : contactsLoading ? (
                  <Text variant="caption" color="secondary">
                    Loading customers…
                  </Text>
                ) : contacts.length === 0 ? (
                  <Text testID="job-create-no-contacts" variant="caption" color="secondary">
                    No customers yet — switch to "New customer" above.
                  </Text>
                ) : (
                  <View className="gap-2">
                    {contacts.map((contact) => {
                      const selected = contact.id === contactId;
                      return (
                        <Pressable
                          key={contact.id}
                          testID={`job-create-contact-${contact.id}`}
                          onPress={() => setContactId(contact.id)}
                        >
                          <View
                            className={`rounded-xl border p-3 ${
                              selected
                                ? "border-blue-500 bg-blue-50"
                                : "border-slate-200 bg-white"
                            }`}
                          >
                            <Text variant="body" weight={selected ? "semibold" : "normal"}>
                              {contact.name}
                            </Text>
                            {contact.postcode ? (
                              <Text variant="caption" color="secondary">
                                {contact.postcode}
                              </Text>
                            ) : null}
                          </View>
                        </Pressable>
                      );
                    })}
                  </View>
                )}
              </>
            )}
          </View>

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

          {DATE_RE.test(date.trim()) && (
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
                  <View className="rounded-xl border border-blue-100 bg-blue-50 p-3">
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
              selectedQuote
                ? "Prefilled from the quote's labour hours — edit if the plan changed."
                : "Optional — sets the job's end time from the start."
            }
            error={durationValid ? null : "Enter a positive number of hours, e.g. 8"}
            keyboardType="decimal-pad"
          />

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
            disabled={busy}
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
