import { useLocalSearchParams, useRouter } from "expo-router";
import { CustomerInvoiceDetailScreen } from "../../../src/screens/customer/CustomerInvoiceDetailScreen";
import { useMyInvoice } from "../../../src/api/customerInvoices";

export default function CustomerInvoiceDetailRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const { invoice } = useMyInvoice(id);

  if (!invoice) return null;

  const handleBack = () => {
    // A push-notification tap can land here with no back stack.
    if (router.canGoBack()) router.back();
    else router.replace("/(customer)/invoices");
  };

  return <CustomerInvoiceDetailScreen invoice={invoice} onBack={handleBack} />;
}
