import { useState } from "react";
import { Pressable, StyleSheet, TextInput, View } from "react-native";
import { Button } from "../../../components/ui/Button";
import { FileUploadPlaceholder } from "../../../components/ui/FileUploadPlaceholder";
import { Icon } from "../../../components/ui/Icon";
import { Text } from "../../../components/ui/Text";
import { StepPropsWithBusiness } from "./types";

const PROPERTY_TYPES = [
  { key: "detached", label: "Detached" },
  { key: "semi", label: "Semi-detached" },
  { key: "terrace", label: "Terrace" },
  { key: "bungalow", label: "Bungalow" },
  { key: "flat", label: "Flat" },
];

const PROPERTY_AGES = [
  { key: "pre_1930", label: "Pre-1930" },
  { key: "1930-1960", label: "1930–1960" },
  { key: "1960-1980", label: "1960–1980" },
  { key: "1980-2000", label: "1980–2000" },
  { key: "post_2000", label: "Post-2000" },
  { key: "not_sure", label: "Not sure" },
];

const TENURES = [
  { key: "owner", label: "Owner" },
  { key: "tenant", label: "Tenant" },
  { key: "landlord", label: "Landlord" },
  { key: "housing_assoc", label: "Housing association" },
];

const FUSE_STYLES = [
  { key: "modern_rcbo", label: "Modern RCBO" },
  { key: "rcd_split", label: "RCD split-load" },
  { key: "rewireable", label: "Rewireable fuses" },
  { key: "not_sure", label: "Not sure" },
];

const KNOWN_ISSUES = [
  { key: "tripping", label: "Tripping" },
  { key: "flickering", label: "Flickering lights" },
  { key: "smell", label: "Burning smell" },
  { key: "buzzing", label: "Buzzing" },
  { key: "dead_sockets", label: "Dead sockets" },
];

function Stepper({
  label,
  value,
  onChange,
  min,
  max,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
}) {
  return (
    <View style={styles.stepper}>
      <Text variant="body" weight="semibold" style={styles.stepperLabel}>
        {label}
      </Text>
      <View style={styles.stepperControls}>
        <Button
          title="−"
          variant="outline"
          size="sm"
          onPress={() => onChange(Math.max(min, value - 1))}
          disabled={value <= min}
        />
        <Text variant="subtitle" weight="bold" style={styles.stepperValue}>
          {value}
        </Text>
        <Button
          title="+"
          variant="outline"
          size="sm"
          onPress={() => onChange(Math.min(max, value + 1))}
          disabled={value >= max}
        />
      </View>
    </View>
  );
}

export function PropertyProfileStep({ formData, updateFormData, onNext }: StepPropsWithBusiness) {
  const [property, setProperty] = useState(formData.property);
  const [showAgeTooltip, setShowAgeTooltip] = useState(false);

  const toggleIssue = (key: string) => {
    setProperty((prev) => {
      const issues = prev.knownIssues.includes(key)
        ? prev.knownIssues.filter((k) => k !== key)
        : [...prev.knownIssues, key];
      return { ...prev, knownIssues: issues };
    });
  };

  const handleNext = () => {
    updateFormData({ property });
    onNext();
  };

  const isValid =
    property.type.length > 0 &&
    property.age.length > 0 &&
    property.tenure.length > 0 &&
    property.parking !== null &&
    (property.type !== "flat" || property.flatAccess !== null);

  return (
    <View style={styles.container}>
      <Text variant="title" weight="bold">
        Property profile
      </Text>
      <Text variant="body" color="secondary">
        This helps estimate materials and time for your job.
      </Text>

      <Text variant="body" weight="semibold">
        Property type
      </Text>
      <View style={styles.options}>
        {PROPERTY_TYPES.map((type) => (
          <Button
            key={type.key}
            title={type.label}
            variant={property.type === type.key ? "primary" : "outline"}
            size="sm"
            onPress={() => setProperty((prev) => ({ ...prev, type: type.key }))}
          />
        ))}
      </View>

      <View style={styles.row}>
        <Text variant="body" weight="semibold">
          Property age
        </Text>
        <Pressable onPress={() => setShowAgeTooltip((v) => !v)}>
          <Icon name="info" size={18} color="#6B7280" />
        </Pressable>
      </View>
      {showAgeTooltip ? (
        <Text variant="caption" color="secondary">
          Property age is the biggest factor in estimating wiring condition and likely upgrade scope.
        </Text>
      ) : null}
      <View style={styles.options}>
        {PROPERTY_AGES.map((age) => (
          <Button
            key={age.key}
            title={age.label}
            variant={property.age === age.key ? "primary" : "outline"}
            size="sm"
            onPress={() => setProperty((prev) => ({ ...prev, age: age.key }))}
          />
        ))}
      </View>

      <View style={styles.steppers}>
        <Stepper label="Bedrooms" value={property.bedrooms} onChange={(v) => setProperty((prev) => ({ ...prev, bedrooms: v }))} min={0} max={10} />
        <Stepper label="Receptions" value={property.receptions} onChange={(v) => setProperty((prev) => ({ ...prev, receptions: v }))} min={0} max={10} />
        <Stepper label="Floors" value={property.floors} onChange={(v) => setProperty((prev) => ({ ...prev, floors: v }))} min={1} max={5} />
      </View>

      <Text variant="body" weight="semibold">
        Tenure
      </Text>
      <View style={styles.options}>
        {TENURES.map((tenure) => (
          <Button
            key={tenure.key}
            title={tenure.label}
            variant={property.tenure === tenure.key ? "primary" : "outline"}
            size="sm"
            onPress={() => setProperty((prev) => ({ ...prev, tenure: tenure.key as any }))}
          />
        ))}
      </View>

      {property.type === "flat" ? (
        <>
          <Text variant="body" weight="semibold">
            Lift access?
          </Text>
          <View style={styles.options}>
            <Button
              title="Yes"
              variant={property.flatAccess === true ? "primary" : "outline"}
              size="sm"
              onPress={() => setProperty((prev) => ({ ...prev, flatAccess: true }))}
            />
            <Button
              title="No"
              variant={property.flatAccess === false ? "primary" : "outline"}
              size="sm"
              onPress={() => setProperty((prev) => ({ ...prev, flatAccess: false }))}
            />
          </View>
        </>
      ) : null}

      <Text variant="body" weight="semibold">
        Van parking available?
      </Text>
      <View style={styles.options}>
        <Button
          title="Yes"
          variant={property.parking === true ? "primary" : "outline"}
          size="sm"
          onPress={() => setProperty((prev) => ({ ...prev, parking: true }))}
        />
        <Button
          title="No"
          variant={property.parking === false ? "primary" : "outline"}
          size="sm"
          onPress={() => setProperty((prev) => ({ ...prev, parking: false }))}
        />
      </View>

      <Text variant="body" weight="semibold">
        Consumer unit photo
      </Text>
      <FileUploadPlaceholder
        label={property.consumerUnitPhoto ? "Consumer unit photo added" : "Upload consumer unit photo"}
        testID="quote-consumer-unit-photo"
      />

      <Text variant="body" weight="semibold">
        Fuse board style
      </Text>
      <View style={styles.options}>
        {FUSE_STYLES.map((style) => (
          <Button
            key={style.key}
            title={style.label}
            variant={property.fuseBoardStyle === style.key ? "primary" : "outline"}
            size="sm"
            onPress={() => setProperty((prev) => ({ ...prev, fuseBoardStyle: style.key }))}
          />
        ))}
      </View>

      <Text variant="body" weight="semibold">
        Known issues (select any)
      </Text>
      <View style={styles.options}>
        {KNOWN_ISSUES.map((issue) => (
          <Button
            key={issue.key}
            title={issue.label}
            variant={property.knownIssues.includes(issue.key) ? "primary" : "outline"}
            size="sm"
            onPress={() => toggleIssue(issue.key)}
          />
        ))}
      </View>

      <Button testID="quote-property-continue" title="Continue" onPress={handleNext} disabled={!isValid} />
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
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  steppers: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 16,
  },
  stepper: {
    flex: 1,
    minWidth: 100,
    gap: 8,
  },
  stepperLabel: {
    marginBottom: 4,
  },
  stepperControls: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  stepperValue: {
    minWidth: 24,
    textAlign: "center",
  },
});
