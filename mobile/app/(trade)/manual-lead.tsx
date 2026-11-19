import { useLocalSearchParams, useRouter } from "expo-router";
import { ManualLeadScreen } from "../../src/screens/trade/ManualLeadScreen";
import { Contact } from "../../src/api/contacts";
import { useIntakeCustomerStore } from "../../src/stores/intakeCustomerStore";

export default function ManualLeadRoute() {
  const router = useRouter();
  const { returnTo, name } = useLocalSearchParams<{ returnTo?: string; name?: string }>();
  const setPendingCustomer = useIntakeCustomerStore((s) => s.setPending);

  // Quote-intake loop: stash the saved customer and pop back, so the intake
  // keeps its in-progress form state and pre-selects the new customer.
  const onSaved =
    returnTo === "quote-intake"
      ? (contact: Contact) => {
          setPendingCustomer(contact);
          router.back();
        }
      : undefined;

  return (
    <ManualLeadScreen
      onClose={() => router.back()}
      prefillName={typeof name === "string" && name !== "" ? name : undefined}
      onSaved={onSaved}
    />
  );
}
