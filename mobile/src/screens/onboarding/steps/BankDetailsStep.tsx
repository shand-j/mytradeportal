import { useEffect, useState } from "react";
import { ScrollView, View } from "react-native";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "../../../components/ui/Button";
import { FormField } from "../../../components/ui/FormField";
import { Text } from "../../../components/ui/Text";
import { fetchPaymentDetails, updatePaymentDetails } from "../../../api/businesses";
import { ApiError, NetworkError } from "../../../lib/apiClient";

type BankDetailsStepProps = {
  data?: Record<string, unknown>;
  onNext: (data?: Record<string, unknown>) => void;
};

const SORT_CODE_RE = /^\d{2}-?\d{2}-?\d{2}$/;
const ACCOUNT_NUMBER_RE = /^\d{8}$/;

/**
 * Bank transfer details shown on every invoice (#189) — the same fields as
 * Settings → Payment details, captured here so every tenant has a manual
 * payment method from day one. Runs after the review step, so the tenant
 * already exists and the details save straight to it.
 */
export function BankDetailsStep({ data, onNext }: BankDetailsStepProps) {
  const queryClient = useQueryClient();
  const detailsQuery = useQuery({ queryKey: ["payment-details"], queryFn: fetchPaymentDetails });

  const [accountName, setAccountName] = useState((data?.bankAccountName as string) ?? "");
  const [sortCode, setSortCode] = useState((data?.bankSortCode as string) ?? "");
  const [accountNumber, setAccountNumber] = useState((data?.bankAccountNumber as string) ?? "");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const details = detailsQuery.data;
    if (!details) return;
    setAccountName((prev) => prev || details.bankAccountName || "");
    setSortCode((prev) => prev || details.bankSortCode || "");
    setAccountNumber((prev) => prev || details.bankAccountNumber || "");
  }, [detailsQuery.data]);

  const saveMutation = useMutation({
    mutationFn: updatePaymentDetails,
    onSuccess: (saved) => {
      void queryClient.invalidateQueries({ queryKey: ["payment-details"] });
      void queryClient.invalidateQueries({ queryKey: ["current-tenant"] });
      onNext({ ...saved, saved: true });
    },
    onError: (err) => {
      if (err instanceof NetworkError) {
        setError("Can't reach the server. Check your connection and try again.");
      } else if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError("Couldn't save payment details. Please try again.");
      }
    },
  });

  const save = () => {
    setError(null);
    const trimmedSortCode = sortCode.trim();
    const trimmedAccountNumber = accountNumber.trim();
    if (!SORT_CODE_RE.test(trimmedSortCode)) {
      setError("Sort code must be 6 digits, e.g. 12-34-56");
      return;
    }
    if (!ACCOUNT_NUMBER_RE.test(trimmedAccountNumber)) {
      setError("Account number must be 8 digits");
      return;
    }
    saveMutation.mutate({
      bankAccountName: accountName.trim(),
      bankSortCode: trimmedSortCode,
      bankAccountNumber: trimmedAccountNumber,
    });
  };

  return (
    <ScrollView className="flex-1" keyboardShouldPersistTaps="handled">
      <View className="gap-4 pb-6">
        <Text variant="title" weight="bold">
          Where should customers pay you?
        </Text>
        <Text variant="body" color="secondary">
          These bank details appear on your invoice emails so customers can pay by bank transfer.
        </Text>

        <View className="rounded-2xl bg-slate-100 p-4 gap-3">
          <FormField
            testID="onboarding-payment-account-name"
            label="Account name"
            value={accountName}
            onChangeText={setAccountName}
            placeholder="e.g. J Smith Electrical Ltd"
          />
          <FormField
            testID="onboarding-payment-sort-code"
            label="Sort code"
            value={sortCode}
            onChangeText={setSortCode}
            placeholder="12-34-56"
            keyboardType="number-pad"
            maxLength={8}
          />
          <FormField
            testID="onboarding-payment-account-number"
            label="Account number"
            value={accountNumber}
            onChangeText={setAccountNumber}
            placeholder="12345678"
            keyboardType="number-pad"
            maxLength={8}
          />
          <Text variant="caption" color="secondary">
            The payment reference is set to the invoice number automatically. You can change these
            later in Settings.
          </Text>
        </View>

        {error && (
          <View className="rounded-xl bg-amber-50 p-3">
            <Text testID="onboarding-payment-details-error" variant="caption" color="warning">
              {error}
            </Text>
          </View>
        )}

        <Button
          testID="onboarding-payment-details-save"
          title={saveMutation.isPending ? "Saving…" : "Save & continue"}
          disabled={saveMutation.isPending || !accountName.trim()}
          onPress={save}
        />
      </View>
    </ScrollView>
  );
}
