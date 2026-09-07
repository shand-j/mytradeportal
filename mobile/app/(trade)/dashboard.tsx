import { useNavigationAdapter } from "../../src/hooks/useNavigationAdapter";
import { DashboardScreen } from "../../src/screens/trade/DashboardScreen";

export default function DashboardRoute() {
  const navigation = useNavigationAdapter();
  return <DashboardScreen navigation={navigation} />;
}
