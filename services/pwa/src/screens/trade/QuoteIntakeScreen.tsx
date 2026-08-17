import { useState } from "react";
import { ScrollView, TextInput, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { FileUploadMock } from "../../components/ui/FileUploadMock";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { Lead } from "../../types";

const PROPERTY_TYPES = ["House", "Flat", "Bungalow", "Commercial"];
const BEDROOMS = ["1", "2", "3", "4", "5+"];
const CU_LOCATIONS = ["Hallway", "Kitchen", "Garage", "Utility", "Under stairs", "Other"];

export type QuoteIntakeScreenProps = {
  lead: Lead;
  onBack: () => void;
  onComplete: () => void | Promise<void>;
};

export function QuoteIntakeScreen({ lead, onBack, onComplete }: QuoteIntakeScreenProps) {
  const [propertyType, setPropertyType] = useState("");
  const [bedrooms, setBedrooms] = useState("");
  const [cuLocation, setCuLocation] = useState("");
  const [parking, setParking] = useState("");
  const [access, setAccess] = useState("");
  const [notes, setNotes] = useState(lead.note ?? "");
  const [photoCount, setPhotoCount] = useState(0);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canComplete =
    propertyType.trim() && bedrooms.trim() && cuLocation.trim() && parking.trim() && access.trim();

  const handleComplete = async () => {
    if (!canComplete) return;
    setGenerating(true);
    setError(null);
    try {
      await onComplete();
    } catch {
      setError(
        "We couldn't generate the quote automatically. AI quoting may not be enabled — try again or build the quote manually."
      );
    } finally {
      setGenerating(false);
    }
  };

  const addPhoto = () => setPhotoCount((c) => Math.min(c + 1, 5));

  const renderChipGroup = (
    label: string,
    options: string[],
    selected: string,
    onSelect: (value: string) => void
  ) => (
    <View className="flex-row flex-wrap gap-2">
      {options.map((option) => (
        <Button
          key={option}
          testID={`intake-${label.replace(/\s+/g, "-").toLowerCase()}-${option.toLowerCase().replace(/\+/g, "plus")}`}
          title={option}
          variant={selected === option ? "primary" : "outline"}
          onPress={() => onSelect(option)}
        />
      ))}
    </View>
  );

  return (
    <Screen>
      <Header testID="intake-back" title="Quote intake" onBack={onBack} />

      <ScrollView className="flex-1" contentContainerClassName="gap-3 pb-4">
        <View className="rounded-2xl bg-slate-100 p-4 gap-2">
          <Text variant="body" weight="semibold">
            {lead.title}
          </Text>
          <Text variant="caption" color="secondary">
            {lead.customerName} · {lead.postcode} · {lead.urgency}
          </Text>
        </View>

        <View className="rounded-2xl bg-slate-100 p-4 gap-3">
          <Text variant="body" weight="semibold">
            Property type *
          </Text>
          {renderChipGroup("Property type", PROPERTY_TYPES, propertyType, setPropertyType)}
        </View>

        <View className="rounded-2xl bg-slate-100 p-4 gap-3">
          <Text variant="body" weight="semibold">
            Bedrooms *
          </Text>
          {renderChipGroup("Bedrooms", BEDROOMS, bedrooms, setBedrooms)}
        </View>

        <View className="rounded-2xl bg-slate-100 p-4 gap-3">
          <Text variant="body" weight="semibold">
            Consumer unit location *
          </Text>
          {renderChipGroup("CU location", CU_LOCATIONS, cuLocation, setCuLocation)}
        </View>

        <View className="rounded-2xl bg-slate-100 p-4 gap-2">
          <Text variant="body" weight="semibold">
            Access & parking *
          </Text>
          <TextInput
            className="h-12 rounded-xl border border-slate-200 bg-white px-4 text-base text-slate-900"
            placeholder="e.g. Driveway parking, key-safe code 1234"
            value={parking}
            onChangeText={setParking}
          />
        </View>

        <View className="rounded-2xl bg-slate-100 p-4 gap-2">
          <Text variant="body" weight="semibold">
            Site access notes *
          </Text>
          <TextInput
            className="h-20 rounded-xl border border-slate-200 bg-white px-4 pt-3 text-base text-slate-900"
            placeholder="Any access restrictions, pets, working hours..."
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
          <View className="gap-3">
            {Array.from({ length: photoCount }).map((_, i) => (
              <FileUploadMock key={i} label={`Photo ${i + 1}`} fileName={`photo-${i + 1}.jpg`} />
            ))}
            <Button
              title={photoCount === 0 ? "Add photo" : "Add another photo"}
              variant="outline"
              onPress={addPhoto}
            />
          </View>
        </View>

        {generating && (
          <View className="rounded-2xl bg-slate-100 p-4">
            <Text variant="body" color="secondary" align="center">
              Analysing intake and drafting AI quote…
            </Text>
          </View>
        )}

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
          title={generating ? "Drafting quote…" : "Generate AI quote"}
          onPress={handleComplete}
          disabled={!canComplete || generating}
        />
      </View>
    </Screen>
  );
}
