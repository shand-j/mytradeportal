import { useEffect, useState } from "react";
import { Alert, KeyboardAvoidingView, Platform, ScrollView, TextInput, View } from "react-native";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { CustomerBadges } from "../../components/trade/CustomerBadges";
import {
  Contact,
  TRUST_BADGES,
  TrustBadge,
  blockContact,
  setBadgeOverride,
  unblockContact,
  updateContact,
} from "../../api/contacts";
import { ApiError } from "../../lib/apiClient";
import { formatDateUK } from "../../lib/format";

const CONTACT_METHODS = [
  { key: "in_app_chat", label: "Online chat" },
  { key: "phone", label: "Phone" },
  { key: "email", label: "Email" },
];

export type CustomerDetailScreenProps = {
  contact: Contact;
  onBack: () => void;
  onCreateQuote: () => void;
};

/**
 * Editable customer record (N25/C5): full address, property details and
 * parking/access notes persist on the CRM contact and pre-fill quote/job
 * creation for repeat customers.
 */
export function CustomerDetailScreen({ contact, onBack, onCreateQuote }: CustomerDetailScreenProps) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(contact.name);
  const [email, setEmail] = useState(contact.email ?? "");
  const [phone, setPhone] = useState(contact.phone ?? "");
  const [address, setAddress] = useState(contact.address ?? "");
  const [postcode, setPostcode] = useState(contact.postcode ?? "");
  const [propertyType, setPropertyType] = useState(contact.propertyType ?? "");
  const [bedrooms, setBedrooms] = useState(contact.bedrooms != null ? String(contact.bedrooms) : "");
  const [parkingNotes, setParkingNotes] = useState(contact.parkingNotes ?? "");
  const [accessNotes, setAccessNotes] = useState(contact.accessNotes ?? "");
  const [contactMethod, setContactMethod] = useState(contact.preferredContactMethod ?? "");
  const [notes, setNotes] = useState(contact.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [badgeBusy, setBadgeBusy] = useState(false);
  const [blockBusy, setBlockBusy] = useState(false);

  // Re-sync the form when the query cache delivers a fresher record.
  useEffect(() => {
    setName(contact.name);
    setEmail(contact.email ?? "");
    setPhone(contact.phone ?? "");
    setAddress(contact.address ?? "");
    setPostcode(contact.postcode ?? "");
    setPropertyType(contact.propertyType ?? "");
    setBedrooms(contact.bedrooms != null ? String(contact.bedrooms) : "");
    setParkingNotes(contact.parkingNotes ?? "");
    setAccessNotes(contact.accessNotes ?? "");
    setContactMethod(contact.preferredContactMethod ?? "");
    setNotes(contact.notes ?? "");
  }, [contact]);

  const orNull = (value: string) => (value.trim() === "" ? null : value.trim());
  const parsedBedrooms = bedrooms.trim() === "" ? null : parseInt(bedrooms.trim(), 10);
  const bedroomsValid = parsedBedrooms === null || Number.isFinite(parsedBedrooms);
  const canSave = name.trim().length > 0 && bedroomsValid && !saving;

  const handleSave = async () => {
    if (!canSave) return;
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      await updateContact(contact.id, {
        name: name.trim(),
        email: orNull(email),
        phone: orNull(phone),
        address: orNull(address),
        postcode: orNull(postcode)?.toUpperCase() ?? null,
        propertyType: orNull(propertyType),
        bedrooms: parsedBedrooms,
        parkingNotes: orNull(parkingNotes),
        accessNotes: orNull(accessNotes),
        preferredContactMethod: contactMethod || null,
        notes: orNull(notes),
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["contacts"] }),
        queryClient.invalidateQueries({ queryKey: ["contact", contact.id] }),
      ]);
      setSaved(true);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail : "Couldn't save the customer. Please try again."
      );
    } finally {
      setSaving(false);
    }
  };

  // Badge/block mutations return the full contact; push it straight into the
  // detail cache and refresh the CRM list in the background.
  const applyContactUpdate = (updated: Contact) => {
    queryClient.setQueryData(["contact", contact.id], updated);
    void queryClient.invalidateQueries({ queryKey: ["contacts"] });
  };

  const handleBadgeOverride = async (badge: TrustBadge, value: boolean | null) => {
    if (badgeBusy) return;
    setBadgeBusy(true);
    setError(null);
    try {
      applyContactUpdate(await setBadgeOverride(contact.id, badge, value));
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail : "Couldn't update the badge. Please try again."
      );
    } finally {
      setBadgeBusy(false);
    }
  };

  const performBlockToggle = async () => {
    setBlockBusy(true);
    setError(null);
    try {
      applyContactUpdate(
        contact.isBlocked ? await unblockContact(contact.id) : await blockContact(contact.id)
      );
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.detail
          : `Couldn't ${contact.isBlocked ? "unblock" : "block"} the customer. Please try again.`
      );
    } finally {
      setBlockBusy(false);
    }
  };

  const handleBlockToggle = () => {
    if (contact.isBlocked) {
      Alert.alert(
        "Unblock customer?",
        `${contact.name} will be able to log in, request quotes and message you again.`,
        [
          { text: "Cancel", style: "cancel" },
          { text: "Unblock", onPress: () => void performBlockToggle() },
        ]
      );
    } else {
      Alert.alert(
        "Block customer?",
        `${contact.name} will not be able to log in, request quotes or message you. You can unblock them at any time.`,
        [
          { text: "Cancel", style: "cancel" },
          { text: "Block", style: "destructive", onPress: () => void performBlockToggle() },
        ]
      );
    }
  };

  return (
    <Screen>
      <Header testID="customer-detail-back" title="Customer" onBack={onBack} />

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView
          className="flex-1"
          contentContainerClassName="gap-3 pb-4"
          keyboardShouldPersistTaps="handled"
        >
          <Text variant="caption" color="secondary">
            Customer since {formatDateUK(contact.createdAt)}
            {contact.hasAccount ? " · has app account" : " · no app account (email-only)"}
          </Text>
          <CustomerBadges badges={contact.badges ?? []} isBlocked={contact.isBlocked} />

          {contact.isBlocked && (
            <View testID="customer-blocked-banner" className="rounded-2xl bg-amber-50 p-4 gap-1">
              <Text variant="body" weight="semibold" color="warning">
                Customer blocked
              </Text>
              <Text variant="caption" color="secondary">
                They cannot log in, request quotes or message you.
                {contact.blockedAt ? ` Blocked ${formatDateUK(contact.blockedAt)}.` : ""}
                {contact.blockedReason ? ` Reason: ${contact.blockedReason}` : ""}
              </Text>
            </View>
          )}

          <View className="rounded-2xl bg-slate-100 p-4 gap-3">
            <Text variant="body" weight="semibold">
              Contact details
            </Text>
            <TextInput
              testID="customer-edit-name"
              className="h-12 rounded-xl border border-slate-200 bg-white px-4 text-base text-slate-900"
              value={name}
              onChangeText={setName}
              placeholder="Name"
            />
            <TextInput
              testID="customer-edit-email"
              className="h-12 rounded-xl border border-slate-200 bg-white px-4 text-base text-slate-900"
              value={email}
              onChangeText={setEmail}
              placeholder="Email"
              keyboardType="email-address"
              autoCapitalize="none"
            />
            <TextInput
              testID="customer-edit-phone"
              className="h-12 rounded-xl border border-slate-200 bg-white px-4 text-base text-slate-900"
              value={phone}
              onChangeText={setPhone}
              placeholder="Phone"
              keyboardType="phone-pad"
            />
            <View className="gap-1">
              <Text variant="caption" weight="semibold" color="secondary">
                Preferred contact method
              </Text>
              <View className="flex-row flex-wrap gap-2">
                {CONTACT_METHODS.map((m) => (
                  <Button
                    key={m.key}
                    testID={`customer-contact-method-${m.key}`}
                    title={m.label}
                    size="sm"
                    variant={contactMethod === m.key ? "primary" : "outline"}
                    onPress={() => setContactMethod((prev) => (prev === m.key ? "" : m.key))}
                  />
                ))}
              </View>
            </View>
          </View>

          <View className="rounded-2xl bg-slate-100 p-4 gap-3">
            <Text variant="body" weight="semibold">
              Address
            </Text>
            <TextInput
              testID="customer-edit-address"
              className="h-20 rounded-xl border border-slate-200 bg-white px-4 pt-3 text-base text-slate-900"
              value={address}
              onChangeText={setAddress}
              placeholder="Full address — house/flat, street, town"
              multiline
              textAlignVertical="top"
            />
            <TextInput
              testID="customer-edit-postcode"
              className="h-12 rounded-xl border border-slate-200 bg-white px-4 text-base text-slate-900"
              value={postcode}
              onChangeText={setPostcode}
              placeholder="Postcode"
              autoCapitalize="characters"
            />
          </View>

          <View className="rounded-2xl bg-slate-100 p-4 gap-3">
            <Text variant="body" weight="semibold">
              Property details
            </Text>
            <TextInput
              testID="customer-edit-property-type"
              className="h-12 rounded-xl border border-slate-200 bg-white px-4 text-base text-slate-900"
              value={propertyType}
              onChangeText={setPropertyType}
              placeholder="Property type — e.g. Semi-detached house"
            />
            <TextInput
              testID="customer-edit-bedrooms"
              className="h-12 rounded-xl border border-slate-200 bg-white px-4 text-base text-slate-900"
              value={bedrooms}
              onChangeText={setBedrooms}
              placeholder="Bedrooms"
              keyboardType="number-pad"
            />
            {!bedroomsValid && (
              <Text variant="caption" color="warning">
                Bedrooms must be a whole number.
              </Text>
            )}
          </View>

          <View className="rounded-2xl bg-slate-100 p-4 gap-3">
            <Text variant="body" weight="semibold">
              Parking &amp; access
            </Text>
            <Text variant="caption" color="secondary">
              Saved on the customer record and pre-filled when you create a quote or job for
              them.
            </Text>
            <TextInput
              testID="customer-edit-parking"
              className="h-20 rounded-xl border border-slate-200 bg-white px-4 pt-3 text-base text-slate-900"
              value={parkingNotes}
              onChangeText={setParkingNotes}
              placeholder="Parking — e.g. Driveway for one van, permit zone"
              multiline
              textAlignVertical="top"
            />
            <TextInput
              testID="customer-edit-access"
              className="h-20 rounded-xl border border-slate-200 bg-white px-4 pt-3 text-base text-slate-900"
              value={accessNotes}
              onChangeText={setAccessNotes}
              placeholder="Access — key-safe codes, entry restrictions, pets…"
              multiline
              textAlignVertical="top"
            />
          </View>

          <View className="rounded-2xl bg-slate-100 p-4 gap-2">
            <Text variant="body" weight="semibold">
              Notes
            </Text>
            <TextInput
              testID="customer-edit-notes"
              className="h-20 rounded-xl border border-slate-200 bg-white px-4 pt-3 text-base text-slate-900"
              value={notes}
              onChangeText={setNotes}
              placeholder="Anything else worth remembering…"
              multiline
              textAlignVertical="top"
            />
          </View>

          <View className="rounded-2xl bg-slate-100 p-4 gap-3">
            <Text variant="body" weight="semibold">
              Trust badges
            </Text>
            <Text variant="caption" color="secondary">
              Set automatically from invoice and quote history. Override a badge to force it on
              or off; Auto follows the history again.
            </Text>
            {TRUST_BADGES.map((badge) => {
              const override = contact.badgeOverrides?.[badge.key];
              const mode = override === undefined ? "auto" : override ? "on" : "off";
              const autoOn = (contact.autoBadges ?? []).includes(badge.key);
              const options: { key: "auto" | "on" | "off"; label: string; value: boolean | null }[] = [
                { key: "auto", label: `Auto (${autoOn ? "on" : "off"})`, value: null },
                { key: "on", label: "On", value: true },
                { key: "off", label: "Off", value: false },
              ];
              return (
                <View key={badge.key} className="gap-1">
                  <Text variant="caption" weight="semibold" color="secondary">
                    {badge.label} · {badge.hint}
                  </Text>
                  <View className="flex-row flex-wrap gap-2">
                    {options.map((option) => (
                      <Button
                        key={option.key}
                        testID={`badge-${badge.key}-${option.key}`}
                        title={option.label}
                        size="sm"
                        variant={mode === option.key ? "primary" : "outline"}
                        disabled={badgeBusy}
                        onPress={() => void handleBadgeOverride(badge.key, option.value)}
                      />
                    ))}
                  </View>
                </View>
              );
            })}
          </View>

          <View className="rounded-2xl bg-slate-100 p-4 gap-2">
            <Text variant="body" weight="semibold">
              Blocking
            </Text>
            <Text variant="caption" color="secondary">
              {contact.isBlocked
                ? "This customer is blocked. Unblock to let them log in, request quotes and message you again."
                : "Block this customer to stop them logging in, requesting quotes or messaging you."}
            </Text>
            <Button
              testID={contact.isBlocked ? "customer-unblock" : "customer-block"}
              title={
                blockBusy ? "Working…" : contact.isBlocked ? "Unblock customer" : "Block customer"
              }
              variant="outline"
              disabled={blockBusy}
              onPress={handleBlockToggle}
            />
          </View>

          {error && (
            <View className="rounded-2xl bg-amber-50 p-3">
              <Text testID="customer-edit-error" variant="caption" color="warning">
                {error}
              </Text>
            </View>
          )}
          {saved && !error && (
            <View className="rounded-2xl bg-slate-100 p-3">
              <Text testID="customer-edit-saved" variant="caption" color="secondary" align="center">
                Saved.
              </Text>
            </View>
          )}
        </ScrollView>

        <View className="border-t border-slate-200 bg-white pt-4 pb-2 gap-3">
          <Button
            testID="customer-edit-save"
            title={saving ? "Saving…" : "Save changes"}
            onPress={() => void handleSave()}
            disabled={!canSave}
          />
          <Button
            testID="customer-detail-create-quote"
            title="Create quote"
            variant="outline"
            onPress={onCreateQuote}
          />
        </View>
      </KeyboardAvoidingView>
    </Screen>
  );
}
