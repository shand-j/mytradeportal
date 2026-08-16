import { useLocalSearchParams, useRouter } from "expo-router";
import { QuoteEditScreen } from "../../../src/screens/trade/QuoteEditScreen";
import { MOCK_QUOTES } from "../../../src/data/mockQuotes";

export default function QuoteDetailRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const quote = MOCK_QUOTES.find((q) => q.id === id);

  if (!quote) return null;

  return <QuoteEditScreen seed={quote} onClose={() => router.back()} />;
}
