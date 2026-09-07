import { useRouter } from "expo-router";
import { BrandingSettingsScreen } from "../../src/screens/trade/BrandingSettingsScreen";

export default function BrandingRoute() {
  const router = useRouter();
  return <BrandingSettingsScreen onClose={() => router.back()} />;
}
