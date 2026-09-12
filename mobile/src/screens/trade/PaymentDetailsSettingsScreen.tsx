import { useEffect, useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, View } from "react-native";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "../../components/ui/Button";
import { FormField } from "../../components/ui/FormField";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { fetchPaymentDetails, updatePaymentDetails } from "../../api/businesses";
import { ApiError, NetworkError } from "../../lib/apiClient";

export type PaymentDetailsSettingsScreenProps = {
  onClose: () => void;
};

const SORT_CODE_RE = /^\d{2}-?\d{2}-?\d{2}$/;
const ACCOUNT_NUMBER_RE = /^\d{8}$/;

export function PaymentDetailsSettingsScreen({ onClose }: PaymentDetailsSettingsScreenProps) {
  const queryClient = useQueryClient();
  const detailsQuery = useQuery({ queryKey: ["payment-details"], queryFn: fetchPaymentDetails });

  const [accountName, setAccountName] = useState("");
  const [sortCode, setSortCode] = useState("");
  const [accountNumber, setAccountNumber] = useState("");
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
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["payment-details"] });
      void queryClient.invalidateQueries({ queryKey: ["current-tenant"] });
      onClose();
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
    if (trimmedSortCode && !SORT_CODE_RE.test(trimmedSortCode)) {
      setError("Sort code must be 6 digits, e.g. 12-34-56");
      return;
    }
    if (trimmedAccountNumber && !ACCOUNT_NUMBER_RE.test(trimmedAccountNumber)) {
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
    <Screen>
      <Header testID="payment-details-back" title="Payment details" onBack={onClose} />

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView
          className="flex-1"
          style={{ minHeight: 0 }}
          contentContainerClassName="gap-4 pb-6"
          keyboardShouldPersistTaps="handled"
        >
          <Text variant="body" color="secondary">
            These bank details appear on your invoice emails so customers can pay by bank transfer.
          </Text>

          <View className="rounded-2xl bg-slate-100 p-4 gap-3">
            <FormField
              testID="payment-account-name"
              label="Account name"
              value={accountName}
              onChangeText={setAccountName}
              placeholder="e.g. J Smith Electrical Ltd"
            />
            <FormField
              testID="payment-sort-code"
              label="Sort code"
              value={sortCode}
              onChangeText={setSortCode}
              placeholder="12-34-56"
              keyboardType="number-pad"
              maxLength={8}
            />
            <FormField
              testID="payment-account-number"
              label="Account number"
              value={accountNumber}
              onChangeText={setAccountNumber}
              placeholder="12345678"
              keyboardType="number-pad"
              maxLength={8}
            />
            <Text variant="caption" color="secondary">
              The payment reference is set to the invoice number automatically.
            </Text>
          </View>

          {error && (
            <View className="rounded-xl bg-amber-50 p-3">
              <Text testID="payment-details-error" variant="caption" color="warning">
                {error}
              </Text>
            </View>
          )}
        </ScrollView>

        <View className="border-t border-slate-200 bg-white pt-4 pb-2 gap-3">
          <Button
            testID="payment-details-save"
            title={saveMutation.isPending ? "Saving…" : "Save payment details"}
            disabled={saveMutation.isPending}
            onPress={save}
          />
        </View>
      </KeyboardAvoidingView>
    </Screen>
  );
}
