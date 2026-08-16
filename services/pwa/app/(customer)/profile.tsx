import { ProfileScreen } from "../../src/screens/customer/ProfileScreen";
import { useNavigationAdapter } from "../../src/hooks/useNavigationAdapter";

export default function CustomerProfileRoute() {
  const navigation = useNavigationAdapter();
  return <ProfileScreen navigation={navigation} />;
}
