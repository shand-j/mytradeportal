import { useMemo, useState } from "react";
import { ScrollView, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { FormField } from "../../components/ui/FormField";
import { Header } from "../../components/ui/Header";
import { Icon } from "../../components/ui/Icon";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { circuitPasses } from "../../lib/certificates";
import { CircuitTestRow } from "../../types";

export type CircuitFormScreenProps = {
  circuit?: CircuitTestRow;
  onSave: (row: CircuitTestRow) => void;
  onCancel: () => void;
};

function parseNumber(value: string): number | null {
  const n = parseFloat(value);
  return Number.isFinite(n) ? n : null;
}

type RuleCheck = {
  key: string;
  label: string;
  /** null = not enough data yet (amber), otherwise pass (green) / fail (red). */
  pass: boolean | null;
};

function RuleRow({ rule }: { rule: RuleCheck }) {
  const color = rule.pass === null ? "#D97706" : rule.pass ? "#16A34A" : "#DC2626";
  const icon = rule.pass === null ? "help" : rule.pass ? "circle-check" : "warning";
  const label = rule.pass === null ? "—" : rule.pass ? "Pass" : "Fail";
  return (
    <View className="flex-row items-center justify-between py-1">
      <Text variant="caption" color="secondary" style={{ flex: 1 }}>
        {rule.label}
      </Text>
      <View className="flex-row items-center gap-1">
        <Icon name={icon} size={14} color={color} />
        <Text variant="caption" weight="bold" style={{ color }}>
          {label}
        </Text>
      </View>
    </View>
  );
}

export function CircuitFormScreen({ circuit, onSave, onCancel }: CircuitFormScreenProps) {
  const [designation, setDesignation] = useState(circuit?.circuit ?? "");
  const [protection, setProtection] = useState(circuit?.protection ?? "");
  const [zsMeasured, setZsMeasured] = useState(circuit ? circuit.zsMeasured.toString() : "");
  const [zsMax, setZsMax] = useState(circuit ? circuit.zsMax.toString() : "");
  const [rcdTripMs, setRcdTripMs] = useState(circuit ? circuit.rcdTripMs.toString() : "");
  const [ir, setIr] = useState(circuit ? circuit.ir.toString() : "");
  const [submitted, setSubmitted] = useState(false);

  const zsMeasuredN = parseNumber(zsMeasured);
  const zsMaxN = parseNumber(zsMax);
  const rcdTripMsN = parseNumber(rcdTripMs);
  const irN = parseNumber(ir);

  // Live BS 7671 rule feedback — same thresholds as circuitPasses.
  const rules: RuleCheck[] = useMemo(
    () => [
      {
        key: "zs",
        label:
          zsMeasuredN != null && zsMaxN != null
            ? `Zs measured ${zsMeasuredN.toFixed(2)}Ω ≤ max ${zsMaxN.toFixed(2)}Ω`
            : "Zs measured ≤ max permitted (BS 7671 tables)",
        pass: zsMeasuredN == null || zsMaxN == null ? null : zsMeasuredN <= zsMaxN,
      },
      {
        key: "rcd",
        label: "RCD disconnection time ≤ 40ms at 5× IΔn",
        pass: rcdTripMsN == null ? null : rcdTripMsN <= 40,
      },
      {
        key: "ir",
        label: "Insulation resistance ≥ 1 MΩ",
        pass: irN == null ? null : irN >= 1,
      },
    ],
    [zsMeasuredN, zsMaxN, rcdTripMsN, irN]
  );

  const allValid =
    designation.trim().length > 0 &&
    protection.trim().length > 0 &&
    zsMeasuredN != null &&
    zsMaxN != null &&
    rcdTripMsN != null &&
    irN != null;

  const overallPass =
    allValid &&
    circuitPasses({
      id: circuit?.id ?? "",
      circuit: designation,
      protection,
      zsMeasured: zsMeasuredN,
      zsMax: zsMaxN,
      rcdTripMs: rcdTripMsN,
      ir: irN,
    });

  const errors = submitted
    ? {
        designation: designation.trim() ? null : "Circuit designation is required",
        protection: protection.trim() ? null : "Protective device is required",
        zsMeasured: zsMeasuredN != null && zsMeasuredN > 0 ? null : "Enter a valid Zs (Ω)",
        zsMax: zsMaxN != null && zsMaxN > 0 ? null : "Enter the max permitted Zs (Ω)",
        rcdTripMs: rcdTripMsN != null && rcdTripMsN >= 0 ? null : "Enter the trip time (ms)",
        ir: irN != null && irN >= 0 ? null : "Enter the insulation resistance (MΩ)",
      }
    : {
        designation: null,
        protection: null,
        zsMeasured: null,
        zsMax: null,
        rcdTripMs: null,
        ir: null,
      };

  const handleSave = () => {
    setSubmitted(true);
    if (!allValid) return;
    onSave({
      id: circuit?.id ?? `ckt-${Date.now()}`,
      circuit: designation.trim(),
      protection: protection.trim(),
      zsMeasured: zsMeasuredN!,
      zsMax: zsMaxN!,
      rcdTripMs: rcdTripMsN!,
      ir: irN!,
    });
  };

  return (
    <Screen>
      <Header title={circuit ? "Edit circuit" : "Add circuit"} onBack={onCancel} />

      <ScrollView
        className="flex-1"
        contentContainerStyle={{ gap: 16, paddingBottom: 32 }}
        keyboardShouldPersistTaps="handled"
      >
        <FormField
          testID="circuit-designation"
          label="Circuit designation"
          value={designation}
          onChangeText={setDesignation}
          placeholder="e.g. Kitchen ring final"
          error={errors.designation}
        />
        <FormField
          testID="circuit-protection"
          label="Protective device"
          value={protection}
          onChangeText={setProtection}
          placeholder="e.g. 32A Type B MCB + 30mA RCD"
          error={errors.protection}
        />

        <View className="flex-row gap-3">
          <View style={{ flex: 1 }}>
            <FormField
              testID="circuit-zs-measured"
              label="Zs measured (Ω)"
              value={zsMeasured}
              onChangeText={setZsMeasured}
              placeholder="0.62"
              keyboardType="decimal-pad"
              error={errors.zsMeasured}
            />
          </View>
          <View style={{ flex: 1 }}>
            <FormField
              testID="circuit-zs-max"
              label="Max Zs (Ω)"
              value={zsMax}
              onChangeText={setZsMax}
              placeholder="1.44"
              keyboardType="decimal-pad"
              error={errors.zsMax}
              helper="BS 7671 tables"
            />
          </View>
        </View>

        <View className="flex-row gap-3">
          <View style={{ flex: 1 }}>
            <FormField
              testID="circuit-rcd-trip"
              label="RCD trip (ms)"
              value={rcdTripMs}
              onChangeText={setRcdTripMs}
              placeholder="28"
              keyboardType="decimal-pad"
              error={errors.rcdTripMs}
              helper="At 5× IΔn"
            />
          </View>
          <View style={{ flex: 1 }}>
            <FormField
              testID="circuit-ir"
              label="IR (MΩ)"
              value={ir}
              onChangeText={setIr}
              placeholder=">200"
              keyboardType="decimal-pad"
              error={errors.ir}
            />
          </View>
        </View>

        {/* Live BS 7671 validation */}
        <View
          className="rounded-2xl border p-4 gap-1"
          style={{
            borderColor: !allValid ? "#FDE68A" : overallPass ? "#BBF7D0" : "#FECACA",
            backgroundColor: !allValid ? "#FFFBEB" : overallPass ? "#F0FDF4" : "#FEF2F2",
          }}
        >
          <View className="flex-row items-center justify-between mb-1">
            <Text variant="body" weight="semibold">
              BS 7671 checks
            </Text>
            <Text
              testID="circuit-overall-result"
              variant="caption"
              weight="bold"
              style={{ color: !allValid ? "#D97706" : overallPass ? "#16A34A" : "#DC2626" }}
            >
              {!allValid ? "INCOMPLETE" : overallPass ? "PASS" : "FAIL"}
            </Text>
          </View>
          {rules.map((rule) => (
            <RuleRow key={rule.key} rule={rule} />
          ))}
        </View>
      </ScrollView>

      <View className="border-t border-slate-200 bg-white pt-4 pb-2 gap-3">
        <Button testID="circuit-save" title={circuit ? "Save circuit" : "Add circuit"} onPress={handleSave} />
        <Button title="Cancel" variant="outline" onPress={onCancel} />
      </View>
    </Screen>
  );
}
