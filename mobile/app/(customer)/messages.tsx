import { useEffect } from "react";
import { View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { MessagesScreen } from "../../src/screens/customer/MessagesScreen";
import { Screen } from "../../src/components/ui/Screen";
import { Header } from "../../src/components/ui/Header";
import { Text } from "../../src/components/ui/Text";
import { fetchMyRequests } from "../../src/api/quoteRequests";

export default function CustomerMessagesRoute() {
  const params = useLocalSearchParams();
  const router = useRouter();
  const quoteRequestId = typeof params.quoteRequestId === "string" ? params.quoteRequestId : undefined;

  // Opened from the tab bar (no thread selected): jump to the customer's most
  // recent conversation so chat is reachable on demand, not only via a quote.
  const requestsQuery = useQuery({
    queryKey: ["my-requests"],
    queryFn: fetchMyRequests,
    enabled: !quoteRequestId,
  });

  const latestThreadId = !quoteRequestId ? requestsQuery.data?.[0]?.id : undefined;

  useEffect(() => {
    if (latestThreadId) {
      router.replace({ pathname: "/(customer)/messages", params: { quoteRequestId: latestThreadId } });
    }
  }, [latestThreadId, router]);

  const handleBack = () => {
    if (router.canGoBack()) {
      router.back();
    } else {
      router.replace("/(customer)/requests");
    }
  };

  if (!quoteRequestId) {
    if (requestsQuery.isLoading) {
      return (
        <Screen>
          <Header title="Messages" onBack={handleBack} />
          <Text variant="caption" color="secondary" align="center">
            Loading conversations…
          </Text>
        </Screen>
      );
    }
    if (requestsQuery.isSuccess) {
      return (
        <Screen>
          <Header title="Messages" onBack={handleBack} />
          <View className="flex-1 items-center justify-center">
            <Text variant="body" color="secondary" align="center">
              No conversations yet.{"\n"}Request a quote and we'll chat there.
            </Text>
          </View>
        </Screen>
      );
    }
  }

  return (
    <MessagesScreen
      quoteRequestId={quoteRequestId}
      senderRole="customer"
      initialComposerText={
        typeof params.initialText === "string" ? params.initialText : undefined
      }
      onBack={handleBack}
    />
  );
}
