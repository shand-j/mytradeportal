import { useLocalSearchParams, useRouter } from "expo-router";
import { QuoteEditScreen } from "../../../src/screens/trade/QuoteEditScreen";
import { MOCK_QUOTES } from "../../../src/data/mockQuotes";
import { useQuote } from "../../../src/api/quotes";

export default function QuoteDetailRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();

  // Connected mode: resolve the real quote; otherwise mock.
  const { quote: realQuote } = useQuote(id);
  const quote = realQuote ?? MOCK_QUOTES.find((q) => q.id === id);

  if (!quote) return null;

  return <QuoteEditScreen seed={quote} onClose={() => router.back()} />;
}
