import { useLocalSearchParams, useRouter } from "expo-router";
import { LoginScreen } from "../src/screens/entry/LoginScreen";

export default function TradeLoginRoute() {
  const router = useRouter();
  const { email } = useLocalSearchParams<{ email?: string }>();
  return <LoginScreen role="trade" initialEmail={email} onBack={() => router.back()} />;
}
