import { useMemo, useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, TextInput, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { OptionChips } from "../../components/ui/OptionChips";
import { PhotoAsset, PhotoPicker } from "../../components/ui/PhotoPicker";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { Lead } from "../../types";
import { formatUrgency } from "../../lib/format";
import { BEDROOMS, PROPERTY_TYPES, matchBedrooms, matchPropertyType } from "../../lib/property";

const CU_LOCATIONS = ["Hallway", "Kitchen", "Garage", "Utility", "Under stairs", "Other"];

export type QuoteIntakeData = {
  propertyType: string;
  bedrooms: string;
  cuLocation: string;
  parking: string;
  access: string;
  notes: string;
  /** Uploaded photo asset URLs (MinIO/S3 keys). */
  photoUrls: string[];
  /** Lead-less mode: optional customer name for the generated contact. */
  customerName?: string;
  /** Lead-less mode: existing CRM contact to attach the quote to. */
  contactId?: string;
  /** Lead-less mode: plain-English job description (required). */
  description?: string;
};

export type QuoteIntakeScreenProps = {
  /** When omitted, the intake creates a quote without a lead. */
  lead?: Lead;
  /** Lead-less mode: prefill the customer from a CRM contact. */
  contact?: QuoteIntakeContact;
  onBack: () => void;
  onComplete: (intake: QuoteIntakeData) => void | Promise<void>;
};

/** CRM contact fields the intake pre-fills from (N25: customer → quote chain). */
export type QuoteIntakeContact = {
  id: string;
  name: string;
  parkingNotes?: string | null;
  accessNotes?: string | null;
  propertyType?: string | null;
  bedrooms?: number | null;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/** Normalise a consumer-unit location onto the intake chips. */
function matchCuLocation(value: unknown): string {
  const normalise = (s: string) =>
    s.toLowerCase().replace(/\bthe\b/g, "").replace(/[^a-z0-9]/g, "");
  const raw = normalise(asString(value));
  if (!raw) return "";
  const hit = CU_LOCATIONS.find((loc) => normalise(loc) === raw);
  return hit ?? "Other";
}

/**
 * Best-effort pre-fill of the intake from data already captured on the lead:
 * the electrician's own earlier intake, the customer wizard's property
 * profile/questionnaire, and facts the AI triage extracted from the chat.
 */
function buildInitialIntake(lead?: Lead, contact?: QuoteIntakeContact): QuoteIntakeData {
  if (!lead) {
    // Existing-customer chain: pre-fill site logistics + property details saved
    // on the CRM record so repeat quotes don't re-ask for them.
    return {
      propertyType: matchPropertyType(contact?.propertyType),
      bedrooms: matchBedrooms(contact?.bedrooms ?? ""),
      cuLocation: "",
      parking: asString(contact?.parkingNotes),
      access: asString(contact?.accessNotes),
      notes: "",
      photoUrls: [],
    };
  }
  const sd = lead.structuredData ?? {};
  const intake = asRecord(sd.electricianIntake ?? sd.electrician_intake);
  const property = asRecord(sd.property);
  const questionnaire = asRecord(sd.questionnaire);
  const aiExtracted = asRecord(sd.aiExtracted ?? sd.ai_extracted);

  const propertyType =
    matchPropertyType(intake.propertyType) ||
    matchPropertyType(property.type) ||
    matchPropertyType(aiExtracted.propertyType ?? aiExtracted.property_type);

  const bedrooms =
    matchBedrooms(intake.bedrooms) ||
    matchBedrooms(property.bedrooms) ||
    matchBedrooms(aiExtracted.bedrooms);

  const parkingFlag = property.parking ?? aiExtracted.parking;
  const aiParkingNote =
    typeof aiExtracted.parking === "string" &&
    !["yes", "no", "true", "false"].includes(aiExtracted.parking.toLowerCase())
      ? aiExtracted.parking
      : "";
  let parking =
    asString(intake.parking) ||
    aiParkingNote ||
    asString(aiExtracted.parkingNotes) ||
    asString(aiExtracted.accessNotes);
  if (!parking) {
    if (parkingFlag === true || asString(parkingFlag).toLowerCase() === "yes") {
      parking = "Customer indicated parking is available";
    } else if (parkingFlag === false || asString(parkingFlag).toLowerCase() === "no") {
      parking = "Customer indicated no parking";
    }
  }

  const knownIssues = Array.isArray(property.knownIssues)
    ? property.knownIssues.filter((v): v is string => typeof v === "string")
    : [];
  const accessParts: string[] = [];
  if (property.flatAccess === true) accessParts.push("Flat access confirmed");
  if (property.flatAccess === false) accessParts.push("No flat access");
  if (knownIssues.length > 0) accessParts.push(`Known issues: ${knownIssues.join(", ")}`);
  const access = asString(intake.access) || accessParts.join(". ");

  // Category-specific location hints for consumer-unit / fuse-board jobs.
  const locationHint =
    intake.cuLocation ||
    questionnaire.location ||
    questionnaire.consumer_unit_location ||
    questionnaire.fuse_board_location ||
    questionnaire.board_location ||
    aiExtracted.cuLocation ||
    aiExtracted.consumerUnitLocation ||
    aiExtracted.cu_location ||
    aiExtracted.consumer_unit_location;
  const cuLocation = matchCuLocation(locationHint);

  return {
    propertyType,
    bedrooms,
    cuLocation,
    parking,
    access,
    notes: asString(intake.notes) || lead.note || "",
    photoUrls: [],
  };
}

export function QuoteIntakeScreen({ lead, contact, onBack, onComplete }: QuoteIntakeScreenProps) {
  const initial = useMemo(() => buildInitialIntake(lead, contact), [lead, contact]);
  const [customerName, setCustomerName] = useState(contact?.name ?? "");
  const [description, setDescription] = useState("");
  const [propertyType, setPropertyType] = useState(initial.propertyType);
  const [bedrooms, setBedrooms] = useState(initial.bedrooms);
  const [cuLocation, setCuLocation] = useState(initial.cuLocation);
  const [parking, setParking] = useState(initial.parking);
  const [access, setAccess] = useState(initial.access);
  const [notes, setNotes] = useState(initial.notes);
  const [photos, setPhotos] = useState<PhotoAsset[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Every intake field is optional: anything left unset is omitted from the
  // site survey and the AI estimates it. Without a lead, the plain-English
  // job description is the only required input (backend needs >= 5 chars).
  const canComplete = lead ? true : description.trim().length >= 5;

  const handleComplete = async () => {
    if (!canComplete) return;
    setSubmitting(true);
    setError(null);
    try {
      // Generation runs asynchronously on the backend; onComplete returns as
      // soon as the job is accepted (202) and the app navigates back to the
      // quotes/leads list, where a banner tracks progress.
      await onComplete({
        propertyType,
        bedrooms,
        cuLocation,
        parking,
        access,
        notes,
        photoUrls: photos.map((p) => p.url),
        customerName: customerName.trim(),
        contactId: contact?.id,
        description: description.trim(),
      });
    } catch {
      setError(
        "We couldn't start the AI quote. AI quoting may not be enabled — try again or build the quote manually."
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Screen>
      <Header testID="intake-back" title="Quote intake" onBack={onBack} />

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView
          className="flex-1"
          contentContainerClassName="gap-3 pb-4"
          keyboardShouldPersistTaps="handled"
        >
        {lead ? (
          <View className="rounded-2xl bg-slate-100 p-4 gap-2">
            <Text variant="body" weight="semibold">
              {lead.title}
            </Text>
            <Text variant="caption" color="secondary">
              {lead.customerName} · {lead.postcode} · {formatUrgency(lead.urgency)}
            </Text>
          </View>
        ) : (
          <>
            <View className="rounded-2xl bg-slate-100 p-4 gap-2">
              <Text variant="body" weight="semibold">
                Customer name
              </Text>
              <TextInput
                testID="intake-customer-name"
                className="h-12 rounded-xl border border-slate-200 bg-white px-4 text-base text-slate-900"
                placeholder="Optional — e.g. Jane Smith"
                value={customerName}
                onChangeText={setCustomerName}
              />
            </View>

            <View className="rounded-2xl bg-slate-100 p-4 gap-2">
              <Text variant="body" weight="semibold">
                Job description *
              </Text>
              <TextInput
                testID="intake-description"
                className="h-24 rounded-xl border border-slate-200 bg-white px-4 pt-3 text-base text-slate-900"
                placeholder="Describe the job in plain English, e.g. Replace consumer unit in a 3-bed semi…"
                value={description}
                onChangeText={setDescription}
                multiline
                textAlignVertical="top"
              />
            </View>
          </>
        )}

        <View className="rounded-2xl bg-primary-50 p-4">
          <Text variant="caption" color="secondary">
            Everything below is optional. Leave a field on “Not sure” (or blank) and the AI will
            estimate it from the job description.
          </Text>
        </View>

        <View className="rounded-2xl bg-slate-100 p-4 gap-3">
          <Text variant="body" weight="semibold">
            Property type
          </Text>
          <OptionChips
            testIDPrefix="intake-property-type"
            options={PROPERTY_TYPES}
            selected={propertyType}
            onSelect={setPropertyType}
          />
        </View>

        <View className="rounded-2xl bg-slate-100 p-4 gap-3">
          <Text variant="body" weight="semibold">
            Bedrooms
          </Text>
          <OptionChips
            testIDPrefix="intake-bedrooms"
            options={BEDROOMS}
            selected={bedrooms}
            onSelect={setBedrooms}
          />
        </View>

        <View className="rounded-2xl bg-slate-100 p-4 gap-3">
          <Text variant="body" weight="semibold">
            Consumer unit location
          </Text>
          <OptionChips
            testIDPrefix="intake-cu-location"
            options={CU_LOCATIONS}
            selected={cuLocation}
            onSelect={setCuLocation}
          />
        </View>

        <View className="rounded-2xl bg-slate-100 p-4 gap-2">
          <Text variant="body" weight="semibold">
            Access & parking
          </Text>
          <TextInput
            testID="intake-parking"
            className="h-12 rounded-xl border border-slate-200 bg-white px-4 text-base text-slate-900"
            placeholder="Optional — e.g. Driveway parking, key-safe code 1234"
            value={parking}
            onChangeText={setParking}
          />
        </View>

        <View className="rounded-2xl bg-slate-100 p-4 gap-2">
          <Text variant="body" weight="semibold">
            Site access notes
          </Text>
          <TextInput
            testID="intake-access"
            className="h-20 rounded-xl border border-slate-200 bg-white px-4 pt-3 text-base text-slate-900"
            placeholder="Optional — access restrictions, pets, working hours..."
            value={access}
            onChangeText={setAccess}
            multiline
            textAlignVertical="top"
          />
        </View>

        <View className="rounded-2xl bg-slate-100 p-4 gap-2">
          <Text variant="body" weight="semibold">
            Additional notes
          </Text>
          <TextInput
            className="h-20 rounded-xl border border-slate-200 bg-white px-4 pt-3 text-base text-slate-900"
            placeholder="Customer mention, existing damage, special requests..."
            value={notes}
            onChangeText={setNotes}
            multiline
            textAlignVertical="top"
          />
        </View>

        <View className="rounded-2xl bg-slate-100 p-4 gap-3">
          <Text variant="body" weight="semibold">
            Photos
          </Text>
          <PhotoPicker photos={photos} onChange={setPhotos} />
        </View>

        {error && (
          <View className="rounded-2xl bg-amber-50 p-4">
            <Text testID="intake-error" variant="caption" color="warning">
              {error}
            </Text>
          </View>
        )}
        </ScrollView>

        <View className="border-t border-slate-200 bg-white pt-4 pb-2 gap-3">
          <Button
            testID="intake-generate-quote"
            title={submitting ? "Starting…" : "Generate AI quote"}
            onPress={handleComplete}
            disabled={!canComplete || submitting}
          />
        </View>
      </KeyboardAvoidingView>
    </Screen>
  );
}
