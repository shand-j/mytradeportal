import { useRouter } from "expo-router";
import { LoginScreen } from "../src/screens/entry/LoginScreen";

export default function CustomerLoginRoute() {
  const router = useRouter();
  return <LoginScreen role="customer" onBack={() => router.back()} />;
}
