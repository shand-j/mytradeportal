import { useRouter } from "expo-router";
import { PaymentDetailsSettingsScreen } from "../../src/screens/trade/PaymentDetailsSettingsScreen";

export default function PaymentDetailsRoute() {
  const router = useRouter();
  return <PaymentDetailsSettingsScreen onClose={() => router.back()} />;
}
