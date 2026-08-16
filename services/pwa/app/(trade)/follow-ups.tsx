import { useRouter } from "expo-router";
import { FollowUpSettingsScreen } from "../../src/screens/trade/FollowUpSettingsScreen";

export default function FollowUpsRoute() {
  const router = useRouter();
  return <FollowUpSettingsScreen onClose={() => router.back()} />;
}
