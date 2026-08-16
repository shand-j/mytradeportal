import { useNavigationAdapter } from "../../src/hooks/useNavigationAdapter";
import { CRMScreen } from "../../src/screens/trade/CRMScreen";

export default function CustomersRoute() {
  const navigation = useNavigationAdapter();
  return <CRMScreen navigation={navigation} />;
}
