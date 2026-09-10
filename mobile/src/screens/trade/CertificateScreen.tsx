import { useMemo, useState } from "react";
import { Pressable, ScrollView, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Icon } from "../../components/ui/Icon";
import { IconButton } from "../../components/ui/IconButton";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { circuitPasses } from "../../lib/certificates";
import { Certificate, CertObservation, CircuitTestRow } from "../../types";
import { CircuitFormScreen } from "./CircuitFormScreen";

type CertificateScreenProps = {
  certificate?: Certificate;
  onClose: () => void;
  onIssued?: (id: string) => void;
};

function CodeBadge({ code }: { code: CertObservation["code"] }) {
  const color =
    code === "C1" ? "#DC2626" : code === "C2" ? "#EA580C" : code === "FI" ? "#7C3AED" : "#0F1E26";
  return (
    <View className="rounded-md px-2 py-0.5" style={{ backgroundColor: color }}>
      <Text variant="caption" weight="bold" style={{ color: "#FFFFFF", fontSize: 11 }}>
        {code}
      </Text>
    </View>
  );
}

function CircuitCard({
  row,
  onPress,
  onDelete,
}: {
  row: CircuitTestRow;
  onPress?: () => void;
  onDelete?: () => void;
}) {
  const pass = circuitPasses(row);
  return (
    <Pressable
      testID={`circuit-card-${row.id}`}
      onPress={onPress}
      disabled={!onPress}
      className="rounded-xl border p-3 gap-1"
      style={{ borderColor: pass ? "#BBF7D0" : "#FECACA", backgroundColor: pass ? "#F0FDF4" : "#FEF2F2" }}
    >
      <View className="flex-row items-center justify-between">
        <Text variant="body" weight="semibold" style={{ flex: 1 }} numberOfLines={1}>
          {row.circuit}
        </Text>
        <View className="flex-row items-center gap-1">
          <Icon name={pass ? "circle-check" : "warning"} size={14} color={pass ? "#16A34A" : "#DC2626"} />
          <Text variant="caption" weight="bold" style={{ color: pass ? "#16A34A" : "#DC2626" }}>
            {pass ? "PASS" : "FAIL"}
          </Text>
          {onDelete && (
            <IconButton
              testID={`circuit-delete-${row.id}`}
              icon="close"
              size={16}
              color="#6B7280"
              onPress={onDelete}
            />
          )}
        </View>
      </View>
      <Text variant="caption" color="secondary">
        {row.protection}
      </Text>
      <View className="flex-row flex-wrap gap-x-4 gap-y-0.5">
        <Text variant="caption" color="secondary">
          Zs {row.zsMeasured.toFixed(2)}Ω / max {row.zsMax.toFixed(2)}Ω
        </Text>
        <Text variant="caption" color="secondary">
          RCD {row.rcdTripMs}ms
        </Text>
        <Text variant="caption" color="secondary">
          IR {row.ir}MΩ
        </Text>
      </View>
    </Pressable>
  );
}

export function CertificateScreen({ certificate, onClose, onIssued }: CertificateScreenProps) {
  const isNew = !certificate;

  const [circuits, setCircuits] = useState<CircuitTestRow[]>(certificate?.circuits ?? []);
  const [observations, setObservations] = useState<CertObservation[]>(
    certificate?.observations ?? []
  );
  const [issued, setIssued] = useState(certificate?.status === "issued");
  const [formOpen, setFormOpen] = useState(false);
  const [editingCircuit, setEditingCircuit] = useState<CircuitTestRow | undefined>(undefined);

  // NOTE: there is no certificates backend endpoint yet (nothing under src/api/),
  // so circuits and observations live in local component state only. The screen is
  // fully usable for drafting and BS 7671 validation on site, but entries are lost
  // when the screen unmounts. Wire persistence here once an API exists.

  const openAddForm = () => {
    setEditingCircuit(undefined);
    setFormOpen(true);
  };

  const openEditForm = (row: CircuitTestRow) => {
    setEditingCircuit(row);
    setFormOpen(true);
  };

  const saveCircuit = (row: CircuitTestRow) => {
    setCircuits((prev) => {
      const exists = prev.some((c) => c.id === row.id);
      return exists ? prev.map((c) => (c.id === row.id ? row : c)) : [...prev, row];
    });
    setFormOpen(false);
    setEditingCircuit(undefined);
  };

  const deleteCircuit = (id: string) => {
    setCircuits((prev) => prev.filter((c) => c.id !== id));
  };

  const allPass = circuits.length > 0 && circuits.every(circuitPasses);
  const hasDanger = observations.some((o) => o.code === "C1" || o.code === "C2");
  const overall: "satisfactory" | "unsatisfactory" | null = useMemo(() => {
    if (circuits.length === 0) return null;
    return allPass && !hasDanger ? "satisfactory" : "unsatisfactory";
  }, [circuits.length, allPass, hasDanger]);

  const signAndIssue = () => {
    const id = `cert-${Date.now()}`;
    // TODO: persist the certificate via the backend API and use the returned id.
    setIssued(true);
    onIssued?.(id);
  };

  if (formOpen) {
    return (
      <CircuitFormScreen
        circuit={editingCircuit}
        onSave={saveCircuit}
        onCancel={() => {
          setFormOpen(false);
          setEditingCircuit(undefined);
        }}
      />
    );
  }

  return (
    <Screen>
      <Header title={isNew ? "New EICR" : "EICR certificate"} onBack={onClose} />

      <ScrollView className="flex-1" contentContainerStyle={{ gap: 16, paddingBottom: 32 }}>
        <View className="rounded-2xl bg-slate-100 p-4 gap-1">
          <Text variant="body" weight="semibold">
            {certificate?.customerName ?? "Customer name"}
          </Text>
          <Text variant="caption" color="secondary">
            {certificate?.address ?? "Property address"} · {certificate?.postcode ?? "Postcode"}
          </Text>
          <Text variant="caption" color="secondary">
            BS 7671 · 18th Edition · EICR
          </Text>
        </View>

        {circuits.length === 0 ? (
          <View className="items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-6">
            <Text variant="body" weight="semibold" align="center">
              No circuits recorded yet
            </Text>
            <Text variant="caption" color="secondary" align="center">
              The schedule of test results will appear here once circuit readings are added. Zs, RCD
              and IR values are validated against BS 7671.
            </Text>
            <View className="self-stretch mt-2">
              <Button testID="cert-add-circuit" title="Add circuit" onPress={openAddForm} />
            </View>
          </View>
        ) : (
          <>
            {/* Overall assessment */}
            <View
              className="flex-row items-center gap-3 rounded-2xl p-4"
              style={{
                backgroundColor: overall === "satisfactory" ? "#ECFDF5" : "#FEF2F2",
                borderWidth: 1,
                borderColor: overall === "satisfactory" ? "#A7F3D0" : "#FECACA",
              }}
            >
              <Icon
                name={overall === "satisfactory" ? "shield" : "warning"}
                size={26}
                color={overall === "satisfactory" ? "#059669" : "#DC2626"}
              />
              <View style={{ flex: 1 }}>
                <Text variant="body" weight="bold">
                  {overall === "satisfactory" ? "Satisfactory" : "Unsatisfactory"}
                </Text>
                <Text variant="caption" color="secondary">
                  {circuits.filter(circuitPasses).length}/{circuits.length} circuits pass · Zs, RCD
                  & IR validated against BS 7671
                </Text>
              </View>
            </View>

            {/* Schedule of test results */}
            <View className="gap-2">
              <Text variant="body" weight="semibold">
                Schedule of test results
              </Text>
              {circuits.map((row) => (
                <CircuitCard
                  key={row.id}
                  row={row}
                  onPress={issued ? undefined : () => openEditForm(row)}
                  onDelete={issued ? undefined : () => deleteCircuit(row.id)}
                />
              ))}
              {!issued && (
                <Button
                  testID="cert-add-circuit"
                  title="+ Add circuit"
                  variant="outline"
                  onPress={openAddForm}
                />
              )}
            </View>

            {/* Observations */}
            {observations.length > 0 && (
              <View className="gap-2 rounded-2xl border border-slate-200 bg-white p-4">
                <Text variant="body" weight="semibold">
                  Observations
                </Text>
                {observations.map((o) => (
                  <View key={o.id} className="flex-row items-start gap-2">
                    <CodeBadge code={o.code} />
                    <Text variant="caption" color="secondary" style={{ flex: 1 }}>
                      {o.text}
                    </Text>
                  </View>
                ))}
              </View>
            )}

            {issued && (
              <View className="flex-row items-center gap-2 rounded-2xl border border-green-200 bg-green-50 p-4">
                <Icon name="circle-check" size={20} color="#16A34A" />
                <Text variant="caption" color="secondary" style={{ flex: 1 }}>
                  Certificate issued
                </Text>
              </View>
            )}
          </>
        )}
      </ScrollView>

      {circuits.length > 0 && !issued && (
        <View className="border-t border-slate-200 bg-white pt-4 pb-2 gap-3">
          <Button
            testID="cert-sign-issue"
            title="Sign & issue certificate"
            onPress={signAndIssue}
          />
        </View>
      )}
      {issued && (
        <View className="border-t border-slate-200 bg-white pt-4 pb-2">
          <Button title="Done" variant="outline" onPress={onClose} />
        </View>
      )}
    </Screen>
  );
}
