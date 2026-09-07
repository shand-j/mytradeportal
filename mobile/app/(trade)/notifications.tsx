import { useRouter } from "expo-router";
import { NotificationsScreen } from "../../src/screens/notifications/NotificationsScreen";

export default function TradeNotificationsRoute() {
  const router = useRouter();
  return <NotificationsScreen role="trade" onBack={() => router.back()} />;
}
