import { useNavigationAdapter } from "../../src/hooks/useNavigationAdapter";
import { CalendarScreen } from "../../src/screens/trade/CalendarScreen";

export default function CalendarRoute() {
  const navigation = useNavigationAdapter();
  return <CalendarScreen navigation={navigation} />;
}
