import { useState } from "react";
import { StyleSheet, TextInput, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { FormField } from "../../../components/ui/FormField";
import { Text } from "../../../components/ui/Text";
import { StepPropsWithBusiness } from "./types";

const CHARGER_PREFERENCES = [
  { key: "no_preference", label: "No preference" },
  { key: "tethered", label: "Tethered cable" },
  { key: "socket", label: "Universal socket" },
  { key: "brand", label: "Specific brand" },
];

const PARKING_LOCATIONS = [
  { key: "driveway", label: "Driveway" },
  { key: "garage", label: "Garage" },
  { key: "street", label: "Street" },
];

const DISTANCES = [
  { key: "under_5m", label: "Under 5 m" },
  { key: "5_10m", label: "5–10 m" },
  { key: "10_20m", label: "10–20 m" },
  { key: "over_20m", label: "Over 20 m" },
];

const SURFACES = [
  { key: "brick", label: "Brick" },
  { key: "render", label: "Render" },
  { key: "timber", label: "Timber" },
  { key: "garage_interior", label: "Garage interior" },
];

const FUSE_RATINGS = [
  { key: "60", label: "60 A" },
  { key: "80", label: "80 A" },
  { key: "100", label: "100 A" },
  { key: "not_sure", label: "Not sure" },
];

const THREE_PHASE = [
  { key: "yes", label: "Yes" },
  { key: "no", label: "No" },
  { key: "not_sure", label: "Not sure" },
];

export function EVChargerQuestionnaire({ formData, updateFormData, onNext }: StepPropsWithBusiness) {
  const [data, setData] = useState<Record<string, any>>(formData.questionnaire.ev_charger ?? {});
  const [notes, setNotes] = useState((formData.questionnaire.notes as string) ?? "");

  const update = (key: string, value: any) => {
    setData((prev) => ({ ...prev, [key]: value }));
  };

  const handleNext = () => {
    updateFormData({
      questionnaire: { ...formData.questionnaire, ev_charger: data, notes },
    });
    onNext();
  };

  const dnoFlag = data.fuse_rating === "60";
  const streetParking = data.parking === "street";

  return (
    <View style={styles.container}>
      <Text variant="title" weight="bold">
        EV charger installation
      </Text>
      <Text variant="body" color="secondary">
        Tell us about your vehicle and installation location.
      </Text>

      <FormField
        label="Vehicle make / model"
        value={data.vehicle ?? ""}
        onChangeText={(text) => update("vehicle", text)}
        placeholder="e.g. Tesla Model 3"
      />

      <Text variant="body" weight="semibold">
        Charger preference
      </Text>
      <View style={styles.options}>
        {CHARGER_PREFERENCES.map((pref) => (
          <Button
            key={pref.key}
            title={pref.label}
            variant={data.preference === pref.key ? "primary" : "outline"}
            size="sm"
            onPress={() => update("preference", pref.key)}
          />
        ))}
      </View>

      <Text variant="body" weight="semibold">
        Parking location
      </Text>
      <View style={styles.options}>
        {PARKING_LOCATIONS.map((loc) => (
          <Button
            key={loc.key}
            title={loc.label}
            variant={data.parking === loc.key ? "primary" : "outline"}
            size="sm"
            onPress={() => update("parking", loc.key)}
          />
        ))}
      </View>
      {streetParking ? (
        <Text variant="caption" color="warning">
          Street parking may need local authority pavement permissions — we’ll advise separately.
        </Text>
      ) : null}

      <Text variant="body" weight="semibold">
        Distance from consumer unit
      </Text>
      <View style={styles.options}>
        {DISTANCES.map((dist) => (
          <Button
            key={dist.key}
            title={dist.label}
            variant={data.distance === dist.key ? "primary" : "outline"}
            size="sm"
            onPress={() => update("distance", dist.key)}
          />
        ))}
      </View>

      <Text variant="body" weight="semibold">
        Mounting surface
      </Text>
      <View style={styles.options}>
        {SURFACES.map((surface) => (
          <Button
            key={surface.key}
            title={surface.label}
            variant={data.surface === surface.key ? "primary" : "outline"}
            size="sm"
            onPress={() => update("surface", surface.key)}
          />
        ))}
      </View>

      <Text variant="body" weight="semibold">
        Main fuse rating
      </Text>
      <View style={styles.options}>
        {FUSE_RATINGS.map((rating) => (
          <Button
            key={rating.key}
            title={rating.label}
            variant={data.fuse_rating === rating.key ? "primary" : "outline"}
            size="sm"
            onPress={() => update("fuse_rating", rating.key)}
          />
        ))}
      </View>
      {dnoFlag ? (
        <Text variant="caption" color="warning">
          A 60 A fuse may need a DNO upgrade before installing an EV charger.
        </Text>
      ) : null}

      <Text variant="body" weight="semibold">
        Wi-Fi at charger location?
      </Text>
      <View style={styles.options}>
        <Button
          title="Yes"
          variant={data.wifi === true ? "primary" : "outline"}
          size="sm"
          onPress={() => update("wifi", true)}
        />
        <Button
          title="No"
          variant={data.wifi === false ? "primary" : "outline"}
          size="sm"
          onPress={() => update("wifi", false)}
        />
      </View>

      <Text variant="body" weight="semibold">
        Three-phase supply?
      </Text>
      <View style={styles.options}>
        {THREE_PHASE.map((opt) => (
          <Button
            key={opt.key}
            title={opt.label}
            variant={data.three_phase === opt.key ? "primary" : "outline"}
            size="sm"
            onPress={() => update("three_phase", opt.key)}
          />
        ))}
      </View>

      <TextInput
        style={styles.notesInput}
        placeholder="Anything else we should know?"
        value={notes}
        onChangeText={setNotes}
        multiline
        numberOfLines={3}
      />

      <Button testID="quote-ev-continue" title="Continue" onPress={handleNext} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: 16,
  },
  options: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  notesInput: {
    height: 80,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#E5E7EB",
    backgroundColor: "#FFFFFF",
    padding: 12,
    fontSize: 14,
    textAlignVertical: "top",
  },
});
