import { useRouter } from "expo-router";
import { InvoicesScreen } from "../../src/screens/trade/InvoicesScreen";

export default function InvoicesRoute() {
  const router = useRouter();
  return <InvoicesScreen onBack={() => router.back()} />;
}
