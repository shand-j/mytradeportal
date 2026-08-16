import { RequestsScreen } from "../../src/screens/customer/RequestsScreen";
import { useNavigationAdapter } from "../../src/hooks/useNavigationAdapter";

export default function CustomerRequestsRoute() {
  const navigation = useNavigationAdapter();
  return <RequestsScreen navigation={navigation as never} />;
}
