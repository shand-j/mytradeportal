import { useLocalSearchParams, useRouter } from "expo-router";
import { JobCreateScreen } from "../../../src/screens/trade/JobCreateScreen";

export default function JobCreateRoute() {
  const router = useRouter();
  const { quoteId } = useLocalSearchParams<{ quoteId?: string }>();
  return <JobCreateScreen onClose={() => router.back()} initialQuoteId={quoteId} />;
}
