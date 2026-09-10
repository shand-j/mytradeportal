import { useEffect, useState } from "react";
import { Pressable, ScrollView, View } from "react-native";
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

const BRAND_COLOURS = [
  "#F2B100", // hi-vis yellow
  "#0EA5E9", // sky
  "#059669", // emerald
  "#D97706", // amber
  "#DC2626", // red
  "#111827", // slate
];

const HEX_RE = /^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

/** Normalise #RGB/#RRGGBB (any case, # optional) to uppercase #RRGGBB, or null. */
function normaliseHex(raw: string): string | null {
  const match = raw.trim().match(HEX_RE);
  if (!match) return null;
  let digits = match[1];
  if (digits.length === 3) {
    digits = digits
      .split("")
      .map((c) => c + c)
      .join("");
  }
  return `#${digits.toUpperCase()}`;
}

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
  const [primaryColor, setPrimaryColor] = useState("");
  const [hexInput, setHexInput] = useState("");
  const [hexError, setHexError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const pickPreset = (colour: string) => {
    setPrimaryColor(colour);
    setHexInput(colour.toUpperCase());
    setHexError(null);
  };

  const onHexChange = (raw: string) => {
    setHexInput(raw);
    const hex = normaliseHex(raw);
    if (hex) {
      setPrimaryColor(hex);
      setHexError(null);
    } else if (raw.trim().length > 0) {
      setHexError("Enter a valid hex colour, e.g. #F2B100");
    } else {
      setHexError(null);
    }
  };

  useEffect(() => {
    if (!tenant) return;
    setName((prev) => prev || tenant.name || "");
    setPhone((prev) => prev || tenant.contactPhone || "");
    setAddress((prev) => prev || tenant.address || "");
    setPrimaryColor((prev) => prev || tenant.primaryColor || "");
    setHexInput((prev) => prev || (tenant.primaryColor ?? "").toUpperCase());
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
    if (hexError) return;
    saveMutation.mutate({
      name: name.trim() || undefined,
      phone: phone.trim() || undefined,
      address: address.trim() || undefined,
      primaryColor: primaryColor || undefined,
    });
  };

  return (
    <Screen>
      <Header testID="branding-back" title="Branding" onBack={onClose} />

      <ScrollView
        className="flex-1"
        style={{ minHeight: 0 }}
        contentContainerClassName="gap-4 pb-6"
        keyboardShouldPersistTaps="handled"
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
            White-label colour across your customer app, quotes, and emails.
          </Text>
          <View className="flex-row flex-wrap gap-3">
            {BRAND_COLOURS.map((colour) => (
              <Pressable
                key={colour}
                onPress={() => pickPreset(colour)}
                accessibilityLabel={`Brand colour ${colour}`}
              >
                <View
                  className={`h-10 w-10 rounded-full ${primaryColor === colour ? "border-2 border-slate-900" : ""}`}
                  style={{ backgroundColor: colour }}
                />
              </Pressable>
            ))}
          </View>
          <View className="flex-row items-center gap-3">
            <View
              className="h-10 w-10 rounded-full border border-slate-300"
              style={{ backgroundColor: primaryColor || tenant?.primaryColor || "#1B2A32" }}
            />
            <View className="flex-1">
              <FormField
                label="Custom hex colour"
                value={hexInput}
                onChangeText={onHexChange}
                placeholder="#F2B100"
                autoCapitalize="characters"
                error={hexError}
              />
            </View>
          </View>
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
