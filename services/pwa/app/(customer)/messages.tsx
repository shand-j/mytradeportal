import { useLocalSearchParams } from "expo-router";
import { MessagesScreen } from "../../src/screens/customer/MessagesScreen";

export default function CustomerMessagesRoute() {
  const params = useLocalSearchParams();
  const quoteRef = typeof params.quoteRef === "string" ? params.quoteRef : undefined;

  return <MessagesScreen initialComposerText={quoteRef ? `Re: ${quoteRef}` : undefined} />;
}
