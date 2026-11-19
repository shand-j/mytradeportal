import { useRouter } from "expo-router";
import { TeamSettingsScreen } from "../../src/screens/trade/TeamSettingsScreen";

export default function TeamRoute() {
  const router = useRouter();
  return <TeamSettingsScreen onClose={() => router.back()} />;
}
