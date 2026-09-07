import { useEffect, useState } from "react";
import { ScrollView, View } from "react-native";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "../../components/ui/Button";
import { FormField } from "../../components/ui/FormField";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { fetchCurrentTenant, updateCurrentTenant } from "../../api/businesses";
import { ApiError, NetworkError } from "../../lib/apiClient";
import { useBusiness } from "../../theme/ThemeProvider";

export type BrandingSettingsScreenProps = {
  onClose: () => void;
};

export function BrandingSettingsScreen({ onClose }: BrandingSettingsScreenProps) {
  const { business, setBusiness } = useBusiness();
  const queryClient = useQueryClient();

  // Pre-fill from the live tenant record (GET /tenants/me); fall back to the
  // branding config already loaded into the business store.
  const tenantQuery = useQuery({ queryKey: ["current-tenant"], queryFn: fetchCurrentTenant });
  const tenant = tenantQuery.data ?? business;

  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!tenant) return;
    setName((prev) => prev || tenant.name || "");
    setPhone((prev) => prev || tenant.contactPhone || "");
    setAddress((prev) => prev || tenant.address || "");
  }, [tenant]);

  const saveMutation = useMutation({
    mutationFn: updateCurrentTenant,
    onSuccess: (updated) => {
      setBusiness({ ...(business ?? updated), ...updated });
      void queryClient.invalidateQueries({ queryKey: ["current-tenant"] });
      onClose();
    },
    onError: (err) => {
      if (err instanceof NetworkError) {
        setError("Can't reach the server. Check your connection and try again.");
      } else if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError("Couldn't save branding. Please try again.");
      }
    },
  });

  const save = () => {
    setError(null);
    saveMutation.mutate({
      name: name.trim() || undefined,
      phone: phone.trim() || undefined,
      address: address.trim() || undefined,
    });
  };

  return (
    <Screen>
      <Header testID="branding-back" title="Branding" onBack={onClose} />

      <ScrollView
        className="flex-1"
        style={{ minHeight: 0 }}
        contentContainerClassName="gap-4 pb-6"
      >
        <View className="rounded-2xl bg-slate-100 p-4 gap-3">
          <FormField label="Business name" value={name} onChangeText={setName} placeholder="Business name" />
          <FormField
            label="Contact phone"
            value={phone}
            onChangeText={setPhone}
            placeholder="Phone"
            keyboardType="phone-pad"
          />
          <FormField label="Address" value={address} onChangeText={setAddress} placeholder="Address" />
        </View>

        <View className="rounded-2xl bg-slate-100 p-4 gap-3">
          <Text variant="body" weight="semibold">
            Primary colour
          </Text>
          <Text variant="caption" color="secondary">
            White-label colour preview:
          </Text>
          <View className="h-12 rounded-xl" style={{ backgroundColor: tenant?.primaryColor ?? "#2563EB" }} />
        </View>

        {error && (
          <View className="rounded-xl bg-amber-50 p-3">
            <Text testID="branding-error" variant="caption" color="warning">
              {error}
            </Text>
          </View>
        )}
      </ScrollView>

      <View className="border-t border-slate-200 bg-white pt-4 pb-2 gap-3">
        <Button
          testID="branding-save"
          title={saveMutation.isPending ? "Saving…" : "Save branding"}
          disabled={saveMutation.isPending}
          onPress={save}
        />
      </View>
    </Screen>
  );
}
