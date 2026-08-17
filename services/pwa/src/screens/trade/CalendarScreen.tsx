import { useMemo, useState } from "react";
import { Pressable, ScrollView, View } from "react-native";
import { useRouter } from "expo-router";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { IconButton } from "../../components/ui/IconButton";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { MOCK_JOBS } from "../../data/mockJobs";
import { useJobsList } from "../../api/jobs";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const DATES = [17, 18, 19, 20, 21, 22, 23];

export type CalendarScreenProps = {
  navigation?: {
    navigate: (name: string, params?: Record<string, unknown>) => void;
  };
};

export function CalendarScreen(_props: CalendarScreenProps) {
  const router = useRouter();
  const [selectedDay, setSelectedDay] = useState(0);
  const [viewMode, setViewMode] = useState<"day" | "week">("day");

  // Connected mode: real jobs from the backend; otherwise mock bookings.
  const { jobs: liveJobs, isConnected } = useJobsList();
  const jobs = isConnected ? liveJobs : MOCK_JOBS;

  const dayBookings = useMemo(
    () => jobs.filter((_, index) => index % 7 === selectedDay),
    [jobs, selectedDay]
  );

  return (
    <Screen>
      <Header
        title="Calendar"
        rightAction={
          <View className="flex-row items-center gap-2">
            {isConnected && (
              <View className="flex-row items-center gap-1 rounded-full bg-green-100 px-2 py-0.5">
                <View className="h-1.5 w-1.5 rounded-full bg-green-600" />
                <Text variant="caption" style={{ color: "#15803D", fontSize: 9 }}>
                  LIVE
                </Text>
              </View>
            )}
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
            {viewMode === "week" ? `Mon ${DATES[0]} – Sun ${DATES[6]} Aug` : `${DAYS[selectedDay]} ${DATES[selectedDay]} Aug`}
          </Text>
          <Text variant="caption" color="secondary">
            {dayBookings.length} booking{dayBookings.length === 1 ? "" : "s"}
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

      {viewMode === "day" && (
        <>
          <View className="flex-row justify-between gap-1.5">
            {DAYS.map((day, index) => (
              <Pressable key={day} className="flex-1" onPress={() => setSelectedDay(index)}>
                <View
                  className={`items-center justify-center gap-1 rounded-xl py-2 ${selectedDay === index ? "bg-blue-100" : "bg-gray-100"}`}
                >
                  <Text variant="caption" color={selectedDay === index ? "text" : "secondary"}>
                    {day.slice(0, 1)}
                  </Text>
                  <Text variant="body" weight={selectedDay === index ? "bold" : "normal"}>
                    {DATES[index]}
                  </Text>
                </View>
              </Pressable>
            ))}
          </View>
          <ScrollView className="flex-1" contentContainerStyle={{ paddingBottom: 24, gap: 12 }}>
            <Text variant="body" weight="semibold">
              Bookings
            </Text>
            {dayBookings.map((booking) => (
              <Pressable key={booking.id} onPress={() => router.push(`/(trade)/job/${booking.id}`)}>
                <View testID={`booking-${booking.id}`} className="flex-row items-center gap-3 rounded-2xl border border-gray-200 bg-white p-4">
                  <View className="h-10 w-1 rounded bg-emerald-500" />
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
        <ScrollView className="flex-1" contentContainerStyle={{ paddingBottom: 24, gap: 12 }}>
          <View className="flex-row gap-3">
            {DAYS.map((day, index) => {
              const dayJobs = jobs.filter((_, i) => i % 7 === index);
              return (
                <View key={day} className="flex-1 overflow-hidden rounded-2xl border border-gray-200 bg-white">
                  <View className="gap-0.5 bg-gray-100 p-2">
                    <Text variant="caption" weight="semibold" align="center">
                      {day}
                    </Text>
                    <Text variant="caption" color="secondary" align="center">
                      {DATES[index]} Aug
                    </Text>
                  </View>
                  <View className="gap-2 p-3">
                    {dayJobs.map((job) => (
                      <Pressable key={job.id} onPress={() => router.push(`/(trade)/job/${job.id}`)}>
                        <View className="gap-0.5 rounded-lg bg-blue-50 p-2">
                          <Text variant="caption" weight="semibold" numberOfLines={1}>
                            {job.time}
                          </Text>
                          <Text variant="caption" color="secondary" numberOfLines={1}>
                            {job.title}
                          </Text>
                        </View>
                      </Pressable>
                    ))}
                    {dayJobs.length === 0 && (
                      <Text variant="caption" color="secondary" align="center">
                        —
                      </Text>
                    )}
                  </View>
                </View>
              );
            })}
          </View>
        </ScrollView>
      )}
    </Screen>
  );
}
