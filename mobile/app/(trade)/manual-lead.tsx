import { useRouter } from "expo-router";
import { ManualLeadScreen } from "../../src/screens/trade/ManualLeadScreen";

export default function ManualLeadRoute() {
  const router = useRouter();
  return <ManualLeadScreen onClose={() => router.back()} />;
}
