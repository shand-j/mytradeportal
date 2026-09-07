import { useLocalSearchParams, useRouter } from "expo-router";
import { ResetPasswordScreen } from "../src/screens/entry/ResetPasswordScreen";

export default function ResetPasswordRoute() {
  const router = useRouter();
  const params = useLocalSearchParams<{ token?: string }>();
  const token = typeof params.token === "string" ? params.token : null;
  return <ResetPasswordScreen token={token} onBack={() => router.back()} />;
}
