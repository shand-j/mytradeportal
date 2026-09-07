import { useRouter } from "expo-router";
import { NotificationsScreen } from "../../src/screens/notifications/NotificationsScreen";

export default function CustomerNotificationsRoute() {
  const router = useRouter();
  return <NotificationsScreen role="customer" onBack={() => router.back()} />;
}
