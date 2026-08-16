import { useLocalSearchParams, useRouter } from "expo-router";
import { MessagesScreen } from "../../src/screens/customer/MessagesScreen";

export default function CustomerMessagesRoute() {
  const params = useLocalSearchParams();
  const router = useRouter();
  const quoteRef = typeof params.quoteRef === "string" ? params.quoteRef : undefined;

  const handleBack = () => {
    if (router.canGoBack()) {
      router.back();
    } else {
      router.replace("/(customer)/requests");
    }
  };

  return (
    <MessagesScreen
      initialComposerText={quoteRef ? `Re: ${quoteRef}` : undefined}
      onBack={handleBack}
    />
  );
}
