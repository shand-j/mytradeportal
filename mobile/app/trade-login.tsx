import { useRouter } from "expo-router";
import { LoginScreen } from "../src/screens/entry/LoginScreen";

export default function TradeLoginRoute() {
  const router = useRouter();
  return <LoginScreen role="trade" onBack={() => router.back()} />;
}
