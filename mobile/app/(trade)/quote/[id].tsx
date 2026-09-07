import { useLocalSearchParams, useRouter } from "expo-router";
import { QuoteEditScreen } from "../../../src/screens/trade/QuoteEditScreen";
import { useQuote, useConvertQuoteToInvoice } from "../../../src/api/quotes";

export default function QuoteDetailRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();

  const { quote: realQuote } = useQuote(id);
  const convert = useConvertQuoteToInvoice();

  if (!realQuote) return null;

  const handleConvertToInvoice = async () => {
    const { id: invoiceId } = await convert.mutateAsync(realQuote.id);
    router.replace(`/(trade)/invoice/${invoiceId}`);
  };

  return (
    <QuoteEditScreen
      seed={realQuote}
      onClose={() => router.back()}
      onRequestMoreInfo={
        realQuote.quoteRequestId
          ? () => router.push(`/(trade)/messages?quoteRequestId=${realQuote.quoteRequestId}`)
          : undefined
      }
      onConvertToInvoice={handleConvertToInvoice}
    />
  );
}
