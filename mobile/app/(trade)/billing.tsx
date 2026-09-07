import { useRouter } from "expo-router";
import { View } from "react-native";
import { Header } from "../../src/components/ui/Header";
import { Screen } from "../../src/components/ui/Screen";
import { PlanPaymentStep } from "../../src/screens/onboarding/steps/PlanPaymentStep";

export default function BillingRoute() {
  const router = useRouter();
  return (
    <Screen>
      <Header title="Subscription" onBack={() => router.back()} />
      <View className="flex-1 pt-2">
        <PlanPaymentStep onNext={() => router.back()} />
      </View>
    </Screen>
  );
}
