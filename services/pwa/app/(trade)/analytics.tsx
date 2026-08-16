import { useRouter } from "expo-router";
import { AnalyticsScreen } from "../../src/screens/trade/AnalyticsScreen";

export default function AnalyticsRoute() {
  const router = useRouter();
  return <AnalyticsScreen onBack={() => router.back()} />;
}
