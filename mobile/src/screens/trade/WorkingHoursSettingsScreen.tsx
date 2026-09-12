import { useEffect, useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from "react-native";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "../../components/ui/Button";
import { FormField } from "../../components/ui/FormField";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { fetchWorkingHours, updateWorkingHours } from "../../api/businesses";
import { ApiError, NetworkError } from "../../lib/apiClient";

export type WorkingHoursSettingsScreenProps = {
  onClose: () => void;
};

const TIME_RE = /^([01]\d|2[0-3]):[0-5]\d$/;

/** Weekday chips, Monday first (backend uses Monday = 0 ... Sunday = 6). */
const DAY_LABELS: { day: number; label: string }[] = [
  { day: 0, label: "Mon" },
  { day: 1, label: "Tue" },
  { day: 2, label: "Wed" },
  { day: 3, label: "Thu" },
  { day: 4, label: "Fri" },
  { day: 5, label: "Sat" },
  { day: 6, label: "Sun" },
];

export function WorkingHoursSettingsScreen({ onClose }: WorkingHoursSettingsScreenProps) {
  const queryClient = useQueryClient();
  const hoursQuery = useQuery({ queryKey: ["working-hours"], queryFn: fetchWorkingHours });

  const [start, setStart] = useState("08:00");
  const [end, setEnd] = useState("18:00");
  const [days, setDays] = useState<number[]>([0, 1, 2, 3, 4, 5, 6]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const hours = hoursQuery.data;
    if (!hours) return;
    setStart(hours.workingDayStart);
    setEnd(hours.workingDayEnd);
    setDays(hours.workingDays);
  }, [hoursQuery.data]);

  const saveMutation = useMutation({
    mutationFn: updateWorkingHours,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["working-hours"] });
      void queryClient.invalidateQueries({ queryKey: ["current-tenant"] });
      onClose();
    },
    onError: (err) => {
      if (err instanceof NetworkError) {
        setError("Can't reach the server. Check your connection and try again.");
      } else if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError("Couldn't save working hours. Please try again.");
      }
    },
  });

  const toggleDay = (day: number) => {
    setDays((current) =>
      current.includes(day) ? current.filter((d) => d !== day) : [...current, day].sort()
    );
  };

  const save = () => {
    setError(null);
    const trimmedStart = start.trim();
    const trimmedEnd = end.trim();
    if (!TIME_RE.test(trimmedStart) || !TIME_RE.test(trimmedEnd)) {
      setError("Times must be 24-hour HH:MM, e.g. 08:00 or 17:30.");
      return;
    }
    if (trimmedStart >= trimmedEnd) {
      setError("The working day must end after it starts.");
      return;
    }
    if (days.length === 0) {
      setError("Pick at least one working day.");
      return;
    }
    saveMutation.mutate({
      workingDayStart: trimmedStart,
      workingDayEnd: trimmedEnd,
      workingDays: days,
    });
  };

  return (
    <Screen>
      <Header testID="working-hours-back" title="Working hours" onBack={onClose} />

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView
          className="flex-1"
          style={{ minHeight: 0 }}
          contentContainerClassName="gap-4 pb-6"
          keyboardShouldPersistTaps="handled"
        >
          <Text variant="body" color="secondary">
            Your working hours decide which slots are offered when scheduling jobs and
            appointments.
          </Text>

          <View className="rounded-2xl bg-slate-100 p-4 gap-3">
            <Text variant="body" weight="semibold">
              Working day
            </Text>
            <FormField
              testID="working-hours-start"
              label="Start of day"
              value={start}
              onChangeText={setStart}
              placeholder="08:00"
              keyboardType="default"
              maxLength={5}
              helper="24-hour time, e.g. 08:00."
            />
            <FormField
              testID="working-hours-end"
              label="End of day"
              value={end}
              onChangeText={setEnd}
              placeholder="18:00"
              keyboardType="default"
              maxLength={5}
              helper="24-hour time, e.g. 17:30."
            />
          </View>

          <View className="rounded-2xl bg-slate-100 p-4 gap-3">
            <Text variant="body" weight="semibold">
              Working days
            </Text>
            <Text variant="caption" color="secondary">
              Days outside your working week are never offered as slots.
            </Text>
            <View className="flex-row flex-wrap gap-2">
              {DAY_LABELS.map(({ day, label }) => {
                const selected = days.includes(day);
                return (
                  <Pressable
                    key={day}
                    testID={`working-hours-day-${day}`}
                    onPress={() => toggleDay(day)}
                  >
                    <View
                      className={`rounded-full px-4 py-2 border ${
                        selected ? "bg-primary border-primary" : "bg-white border-slate-200"
                      }`}
                    >
                      <Text variant="body" weight={selected ? "semibold" : "normal"}>
                        {label}
                      </Text>
                    </View>
                  </Pressable>
                );
              })}
            </View>
          </View>

          {error && (
            <View className="rounded-xl bg-amber-50 p-3">
              <Text testID="working-hours-error" variant="caption" color="warning">
                {error}
              </Text>
            </View>
          )}
        </ScrollView>

        <View className="border-t border-slate-200 bg-white pt-4 pb-2 gap-3">
          <Button
            testID="working-hours-save"
            title={saveMutation.isPending ? "Saving…" : "Save working hours"}
            disabled={saveMutation.isPending}
            onPress={save}
          />
        </View>
      </KeyboardAvoidingView>
    </Screen>
  );
}
