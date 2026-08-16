import { useRouter } from "expo-router";
import { useNavigationAdapter } from "../../src/hooks/useNavigationAdapter";
import { LeadsScreen } from "../../src/screens/trade/LeadsScreen";

export default function LeadsRoute() {
  const router = useRouter();
  const navigation = useNavigationAdapter();
  return <LeadsScreen navigation={navigation} onBack={() => router.back()} />;
}
