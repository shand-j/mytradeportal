import { useState } from "react";
import { Pressable, ScrollView, View } from "react-native";
import { useRouter } from "expo-router";
import { Button } from "../../components/ui/Button";
import { FormField } from "../../components/ui/FormField";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { useContactsList } from "../../api/contacts";
import { useCreateJob } from "../../api/jobs";
import { ApiError } from "../../lib/apiClient";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const TIME_RE = /^\d{2}:\d{2}$/;

export type JobCreateScreenProps = {
  onClose: () => void;
};

/** Minimal manual job entry: title, customer, schedule, notes. */
export function JobCreateScreen({ onClose }: JobCreateScreenProps) {
  const router = useRouter();
  const { contacts, isLoading: contactsLoading } = useContactsList();
  const createJob = useCreateJob();

  const [title, setTitle] = useState("");
  const [contactId, setContactId] = useState<string | null>(null);
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  const dateValid = date.trim() === "" || DATE_RE.test(date.trim());
  const timeValid = time.trim() === "" || TIME_RE.test(time.trim());

  const handleCreate = async () => {
    setError(null);
    if (!title.trim()) {
      setError("Enter a job title.");
      return;
    }
    if (!contactId) {
      setError("Pick a customer.");
      return;
    }
    let scheduledStart: string | undefined;
    if (date.trim() !== "" || time.trim() !== "") {
      if (!DATE_RE.test(date.trim()) || !TIME_RE.test(time.trim())) {
        setError("Enter both a date (YYYY-MM-DD) and a start time (HH:MM).");
        return;
      }
      const start = new Date(`${date.trim()}T${time.trim()}:00`);
      if (Number.isNaN(start.getTime())) {
        setError("That date/time isn't valid.");
        return;
      }
      scheduledStart = start.toISOString();
    }
    try {
      const job = await createJob.mutateAsync({
        contactId,
        title: title.trim(),
        description: notes.trim() !== "" ? notes.trim() : undefined,
        scheduledStart,
      });
      router.replace(`/(trade)/job/${job.id}`);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.detail
          : "Couldn't create the job. Please try again."
      );
    }
  };

  return (
    <Screen>
      <Header testID="job-create-back" title="New job" onBack={onClose} />

      <ScrollView
        className="flex-1"
        style={{ minHeight: 0 }}
        contentContainerClassName="gap-3 pb-4"
        keyboardShouldPersistTaps="handled"
      >
        <FormField
          testID="job-create-title"
          label="Title"
          value={title}
          onChangeText={setTitle}
          placeholder="e.g. Fuse board replacement"
        />

        <View className="gap-1">
          <Text variant="body" weight="semibold">
            Customer
          </Text>
          {contactsLoading ? (
            <Text variant="caption" color="secondary">
              Loading customers…
            </Text>
          ) : contacts.length === 0 ? (
            <Text testID="job-create-no-contacts" variant="caption" color="secondary">
              No customers yet — add one from the Customers tab first.
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
                        selected ? "border-blue-500 bg-blue-50" : "border-slate-200 bg-white"
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
        </View>

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
          title={createJob.isPending ? "Creating…" : "Create job"}
          disabled={createJob.isPending}
          onPress={() => void handleCreate()}
        />
      </View>
    </Screen>
  );
}
