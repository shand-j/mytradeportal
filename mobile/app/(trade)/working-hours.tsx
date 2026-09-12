import { useRouter } from "expo-router";
import { WorkingHoursSettingsScreen } from "../../src/screens/trade/WorkingHoursSettingsScreen";

export default function WorkingHoursRoute() {
  const router = useRouter();
  return <WorkingHoursSettingsScreen onClose={() => router.back()} />;
}
