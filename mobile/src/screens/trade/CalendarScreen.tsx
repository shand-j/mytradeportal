import { useMemo, useState } from "react";
import { Pressable, ScrollView, View } from "react-native";
import { useRouter } from "expo-router";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { IconButton } from "../../components/ui/IconButton";
import { LiveBadge } from "../../components/ui/LiveBadge";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { useJobsList } from "../../api/jobs";
import { Job } from "../../types";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

// Week-grid time window: appointments outside it are clamped to the edges.
const GRID_START_HOUR = 7;
const GRID_END_HOUR = 19;
const HOUR_HEIGHT = 52;
const DEFAULT_DURATION_MIN = 60;

export type CalendarScreenProps = {
  navigation?: {
    navigate: (name: string, params?: Record<string, unknown>) => void;
  };
};

/** Monday 00:00 of the week containing `d`. */
function startOfWeek(d: Date): Date {
  const result = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const dow = (result.getDay() + 6) % 7; // Monday = 0
  result.setDate(result.getDate() - dow);
  return result;
}

function addDays(d: Date, n: number): Date {
  const result = new Date(d);
  result.setDate(result.getDate() + n);
  return result;
}

function toIsoDate(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function formatDay(d: Date): string {
  return `${DAYS[(d.getDay() + 6) % 7]} ${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

/** Minutes since midnight parsed from the app's "HH:MM" display time. */
function parseMinutes(time: string): number | null {
  const match = /^(\d{1,2}):(\d{2})/.exec(time);
  if (!match) return null;
  return parseInt(match[1], 10) * 60 + parseInt(match[2], 10);
}

export function CalendarScreen(_props: CalendarScreenProps) {
  const router = useRouter();
  const today = useMemo(() => new Date(), []);
  const [weekOffset, setWeekOffset] = useState(0);
  const [selectedDay, setSelectedDay] = useState(() => (today.getDay() + 6) % 7);
  const [viewMode, setViewMode] = useState<"day" | "week">("day");

  const { jobs, isLoading } = useJobsList();

  const weekStart = useMemo(() => addDays(startOfWeek(today), weekOffset * 7), [today, weekOffset]);
  const weekDays = useMemo(() => Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)), [weekStart]);

  const jobsByDay = useMemo(() => {
    const map = new Map<string, Job[]>();
    weekDays.forEach((d) => map.set(toIsoDate(d), []));
    for (const job of jobs) {
      if (!job.date) continue;
      const bucket = map.get(job.date);
      if (bucket) bucket.push(job);
    }
    for (const bucket of map.values()) {
      bucket.sort((a, b) => (parseMinutes(a.time) ?? 0) - (parseMinutes(b.time) ?? 0));
    }
    return map;
  }, [jobs, weekDays]);

  const unscheduledJobs = useMemo(() => jobs.filter((job) => !job.date), [jobs]);

  const selectedDate = weekDays[selectedDay];
  const dayBookings = jobsByDay.get(toIsoDate(selectedDate)) ?? [];
  const weekBookingCount = useMemo(
    () => weekDays.reduce((sum, d) => sum + (jobsByDay.get(toIsoDate(d))?.length ?? 0), 0),
    [weekDays, jobsByDay]
  );

  const rangeLabel = `${formatDay(weekDays[0])} – ${formatDay(weekDays[6])}`;

  return (
    <Screen>
      <Header
        title="Calendar"
        rightAction={
          <View className="flex-row items-center gap-2">
            {!isLoading && <LiveBadge />}
            <Button
              testID="calendar-new-job"
              title="+"
              size="sm"
              variant="ghost"
              accessibilityLabel="New job"
              onPress={() => router.push("/(trade)/job/new")}
            />
            <IconButton
              testID="calendar-more"
              icon="more"
              size={24}
              color="#374151"
              onPress={() => router.push("/(trade)/settings")}
              accessibilityLabel="Settings"
            />
          </View>
        }
      />
      <View className="flex-row items-start justify-between gap-3">
        <View>
          <Text variant="body" weight="semibold">
            {viewMode === "week" ? rangeLabel : formatDay(selectedDate)}
          </Text>
          <Text variant="caption" color="secondary">
            {viewMode === "week"
              ? `${weekBookingCount} booking${weekBookingCount === 1 ? "" : "s"} this week`
              : `${dayBookings.length} booking${dayBookings.length === 1 ? "" : "s"}`}
          </Text>
        </View>
        <View className="flex-row gap-1.5">
          <Button
            testID="calendar-day"
            title="Day"
            size="sm"
            variant={viewMode === "day" ? "primary" : "outline"}
            onPress={() => setViewMode("day")}
          />
          <Button
            testID="calendar-week"
            title="Week"
            size="sm"
            variant={viewMode === "week" ? "primary" : "outline"}
            onPress={() => setViewMode("week")}
          />
        </View>
      </View>

      <View className="mb-3 flex-row items-center gap-2">
        <Button testID="calendar-prev-week" title="‹" size="sm" variant="outline" onPress={() => setWeekOffset((n) => n - 1)} />
        <Button
          testID="calendar-today"
          title="Today"
          size="sm"
          variant={weekOffset === 0 ? "primary" : "outline"}
          onPress={() => {
            setWeekOffset(0);
            setSelectedDay((today.getDay() + 6) % 7);
          }}
        />
        <Button testID="calendar-next-week" title="›" size="sm" variant="outline" onPress={() => setWeekOffset((n) => n + 1)} />
      </View>

      {viewMode === "day" && (
        <>
          <View className="flex-row justify-between gap-1.5">
            {weekDays.map((date, index) => {
              const isToday = isSameDay(date, today);
              return (
                <Pressable key={toIsoDate(date)} className="flex-1" onPress={() => setSelectedDay(index)}>
                  <View
                    className={`items-center justify-center gap-1 rounded-xl py-2 ${
                      selectedDay === index ? "bg-primary-100" : isToday ? "bg-primary-50" : "bg-gray-100"
                    }`}
                  >
                    <Text variant="caption" color={selectedDay === index ? "text" : "secondary"}>
                      {DAYS[index].slice(0, 1)}
                    </Text>
                    <Text variant="body" weight={selectedDay === index || isToday ? "bold" : "normal"}>
                      {date.getDate()}
                    </Text>
                  </View>
                </Pressable>
              );
            })}
          </View>
          <ScrollView className="flex-1" contentContainerStyle={{ paddingBottom: 24, gap: 12 }}>
            <Text variant="body" weight="semibold">
              Bookings
            </Text>
            {dayBookings.map((booking) => (
              <Pressable key={booking.id} onPress={() => router.push(`/(trade)/job/${booking.id}`)}>
                <View testID={`booking-${booking.id}`} className="flex-row items-center gap-3 rounded-2xl border border-gray-200 bg-white p-4">
                  <View className="h-10 w-1 rounded bg-accent-500" />
                  <View className="flex-1">
                    <Text variant="body" weight="semibold">
                      {booking.time}
                    </Text>
                    <Text variant="body">{booking.title}</Text>
                    <Text variant="caption" color="secondary">
                      {booking.customerName} · {booking.postcode}
                    </Text>
                  </View>
                </View>
              </Pressable>
            ))}
            {dayBookings.length === 0 && (
              <Text variant="caption" color="secondary">
                No bookings on this day.
              </Text>
            )}
          </ScrollView>
        </>
      )}

      {viewMode === "week" && (
        <ScrollView className="flex-1" contentContainerStyle={{ paddingBottom: 24 }}>
          <ScrollView horizontal showsHorizontalScrollIndicator>
            <View>
              {/* Day header row */}
              <View className="flex-row">
                <View style={{ width: 44 }} />
                {weekDays.map((date) => {
                  const isToday = isSameDay(date, today);
                  return (
                    <View
                      key={toIsoDate(date)}
                      className={`items-center gap-0.5 border-b border-gray-200 p-2 ${isToday ? "bg-primary-50" : ""}`}
                      style={{ width: 132 }}
                    >
                      <Text variant="caption" weight={isToday ? "bold" : "semibold"} align="center">
                        {DAYS[(date.getDay() + 6) % 7]}
                      </Text>
                      <View
                        className={`h-7 w-7 items-center justify-center rounded-full ${isToday ? "bg-primary" : ""}`}
                      >
                        <Text
                          variant="caption"
                          align="center"
                          style={isToday ? { color: "#FFFFFF" } : undefined}
                          color={isToday ? undefined : "secondary"}
                        >
                          {date.getDate()}
                        </Text>
                      </View>
                    </View>
                  );
                })}
              </View>

              {/* Time grid */}
              <View className="flex-row">
                <View style={{ width: 44 }}>
                  {Array.from({ length: GRID_END_HOUR - GRID_START_HOUR }, (_, i) => (
                    <View key={i} style={{ height: HOUR_HEIGHT }} className="items-end pr-1">
                      <Text variant="caption" color="secondary" style={{ fontSize: 10 }}>
                        {String(GRID_START_HOUR + i).padStart(2, "0")}:00
                      </Text>
                    </View>
                  ))}
                </View>
                {weekDays.map((date) => {
                  const isToday = isSameDay(date, today);
                  const dayJobs = jobsByDay.get(toIsoDate(date)) ?? [];
                  return (
                    <View
                      key={toIsoDate(date)}
                      className={`border-l border-gray-100 ${isToday ? "bg-primary-50/40" : ""}`}
                      style={{
                        width: 132,
                        height: (GRID_END_HOUR - GRID_START_HOUR) * HOUR_HEIGHT,
                        position: "relative",
                      }}
                    >
                      {Array.from({ length: GRID_END_HOUR - GRID_START_HOUR }, (_, i) => (
                        <View
                          key={i}
                          className="border-t border-gray-100"
                          style={{ position: "absolute", top: i * HOUR_HEIGHT, left: 0, right: 0 }}
                        />
                      ))}
                      {dayJobs.map((job) => {
                        const startMin = parseMinutes(job.time);
                        if (startMin === null) return null;
                        const endMin = job.endTime
                          ? parseMinutes(job.endTime) ?? startMin + DEFAULT_DURATION_MIN
                          : startMin + DEFAULT_DURATION_MIN;
                        const clampedStart = Math.max(startMin, GRID_START_HOUR * 60);
                        const clampedEnd = Math.min(Math.max(endMin, clampedStart + 30), GRID_END_HOUR * 60);
                        const top = ((clampedStart - GRID_START_HOUR * 60) / 60) * HOUR_HEIGHT;
                        const height = Math.max(((clampedEnd - clampedStart) / 60) * HOUR_HEIGHT, 28);
                        return (
                          <Pressable
                            key={job.id}
                            testID={`booking-${job.id}`}
                            onPress={() => router.push(`/(trade)/job/${job.id}`)}
                            style={{ position: "absolute", top, left: 3, right: 3, height }}
                          >
                            <View className="flex-1 gap-0.5 overflow-hidden rounded-lg border border-primary-200 bg-primary-50 p-1.5">
                              <Text variant="caption" weight="semibold" numberOfLines={1} style={{ fontSize: 11 }}>
                                {job.time}
                              </Text>
                              <Text variant="caption" color="secondary" numberOfLines={2} style={{ fontSize: 11 }}>
                                {job.title}
                              </Text>
                            </View>
                          </Pressable>
                        );
                      })}
                    </View>
                  );
                })}
              </View>
            </View>
          </ScrollView>

          {unscheduledJobs.length > 0 && (
            <View className="mt-4 gap-2">
              <Text variant="body" weight="semibold">
                Unscheduled
              </Text>
              {unscheduledJobs.map((job) => (
                <Pressable key={job.id} onPress={() => router.push(`/(trade)/job/${job.id}`)}>
                  <View className="flex-row items-center gap-3 rounded-2xl border border-gray-200 bg-white p-3">
                    <View className="h-8 w-1 rounded bg-gray-300" />
                    <View className="flex-1">
                      <Text variant="body">{job.title}</Text>
                      <Text variant="caption" color="secondary">
                        {job.customerName}
                      </Text>
                    </View>
                  </View>
                </Pressable>
              ))}
            </View>
          )}
        </ScrollView>
      )}
    </Screen>
  );
}
