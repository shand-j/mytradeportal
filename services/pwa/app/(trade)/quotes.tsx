import { useNavigationAdapter } from "../../src/hooks/useNavigationAdapter";
import { QuotesScreen } from "../../src/screens/trade/QuotesScreen";

export default function QuotesRoute() {
  const navigation = useNavigationAdapter();
  return <QuotesScreen navigation={navigation} />;
}
