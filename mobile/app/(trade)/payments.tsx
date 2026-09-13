import { useRouter } from "expo-router";
import { PaymentsSettingsScreen } from "../../src/screens/trade/PaymentsSettingsScreen";

export default function PaymentsRoute() {
  const router = useRouter();
  return <PaymentsSettingsScreen onClose={() => router.back()} />;
}
