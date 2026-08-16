import { useMemo, useState } from "react";
import { ScrollView, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Icon } from "../../components/ui/Icon";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { VoiceCaptureSheet } from "../../components/VoiceCaptureSheet";
import { MOCK_CERTIFICATES, VOICE_EICR_CIRCUITS, circuitPasses } from "../../data/mockCertificates";
import { useOfflineStore } from "../../stores/offlineStore";
import { Certificate, CertObservation, CircuitTestRow } from "../../types";

const DICTATION =
  "EICR for the three-bed semi. Ring final kitchen, thirty-two amp Type B, Zs measured zero point eight two ohms, " +
  "RCD trip twenty-four milliseconds, insulation two-ninety-nine meg-ohm. Sockets ground floor, zero point nine one. " +
  "Lighting ground floor, six amp, three point one ohms. Cooker circuit, zero point six eight. Immersion, sixteen amp, " +
  "one point four two. One observation: no RCD label at the board, code C3. Overall satisfactory.";

const VOICE_OBSERVATIONS: CertObservation[] = [
  { id: "vo1", code: "C3", text: "No RCD identification label at the consumer unit." },
];

type CertificateScreenProps = {
  certificate?: Certificate;
  onClose: () => void;
  onIssued?: (id: string) => void;
};

function CodeBadge({ code }: { code: CertObservation["code"] }) {
  const color =
    code === "C1" ? "#DC2626" : code === "C2" ? "#EA580C" : code === "FI" ? "#7C3AED" : "#2563EB";
  return (
    <View className="rounded-md px-2 py-0.5" style={{ backgroundColor: color }}>
      <Text variant="caption" weight="bold" style={{ color: "#FFFFFF", fontSize: 11 }}>
        {code}
      </Text>
    </View>
  );
}

function CircuitCard({ row }: { row: CircuitTestRow }) {
  const pass = circuitPasses(row);
  return (
    <View
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
    </View>
  );
}

export function CertificateScreen({ certificate, onClose, onIssued }: CertificateScreenProps) {
  const isNew = !certificate;
  const enqueue = useOfflineStore((s) => s.enqueue);
  const isOnline = useOfflineStore((s) => s.isOnline);

  const [capturing, setCapturing] = useState(false);
  const [circuits, setCircuits] = useState<CircuitTestRow[]>(certificate?.circuits ?? []);
  const [observations, setObservations] = useState<CertObservation[]>(
    certificate?.observations ?? []
  );
  const [issued, setIssued] = useState(certificate?.status === "issued");

  const allPass = circuits.length > 0 && circuits.every(circuitPasses);
  const hasDanger = observations.some((o) => o.code === "C1" || o.code === "C2");
  const overall: "satisfactory" | "unsatisfactory" | null = useMemo(() => {
    if (circuits.length === 0) return null;
    return allPass && !hasDanger ? "satisfactory" : "unsatisfactory";
  }, [circuits.length, allPass, hasDanger]);

  if (capturing) {
    return (
      <VoiceCaptureSheet
        title="Dictate test results"
        prompt="Read out your circuit tests — the AI fills the schedule."
        transcript={DICTATION}
        confirmLabel="test results"
        onCancel={() => setCapturing(false)}
        onComplete={() => {
          setCircuits(VOICE_EICR_CIRCUITS);
          setObservations(VOICE_OBSERVATIONS);
          setCapturing(false);
        }}
      />
    );
  }

  const signAndIssue = () => {
    const id = `cert-${Date.now()}`;
    const cert: Certificate = {
      id,
      type: "EICR",
      customerName: "Jane Homeowner",
      address: "123 Demo Street, Stockport",
      postcode: "SK8 3NJ",
      status: "issued",
      overall,
      circuits,
      observations,
      createdAt: new Date().toISOString(),
      signedBy: "Demo Owner",
      signedAt: new Date().toISOString(),
    };
    MOCK_CERTIFICATES.unshift(cert);
    enqueue("certificate", "EICR — Jane Homeowner, SK8 3NJ");
    setIssued(true);
    onIssued?.(id);
  };

  return (
    <Screen>
      <Header title={isNew ? "New EICR" : "EICR certificate"} onBack={onClose} />

      <ScrollView className="flex-1" contentContainerStyle={{ gap: 16, paddingBottom: 32 }}>
        <View className="rounded-2xl bg-slate-100 p-4 gap-1">
          <Text variant="body" weight="semibold">
            {certificate?.customerName ?? "Jane Homeowner"}
          </Text>
          <Text variant="caption" color="secondary">
            {certificate?.address ?? "123 Demo Street, Stockport"} ·{" "}
            {certificate?.postcode ?? "SK8 3NJ"}
          </Text>
          <Text variant="caption" color="secondary">
            BS 7671 · 18th Edition · EICR
          </Text>
        </View>

        {circuits.length === 0 ? (
          <View className="items-center gap-4 rounded-2xl border border-indigo-100 bg-indigo-50 p-6">
            <View className="h-14 w-14 items-center justify-center rounded-full bg-indigo-600">
              <Icon name="mic" size={28} color="#FFFFFF" />
            </View>
            <Text variant="body" weight="semibold" align="center">
              Dictate your test results
            </Text>
            <Text variant="caption" color="secondary" align="center">
              Read out each circuit and its readings. The AI fills the schedule of test results and
              flags anything that fails BS 7671.
            </Text>
            <Button testID="cert-dictate" title="Dictate test results" onPress={() => setCapturing(true)} />
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
                <CircuitCard key={row.id} row={row} />
              ))}
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
                  Signed by Demo Owner · {isOnline ? "saved to the cloud" : "saved on device, will sync"}
                </Text>
              </View>
            )}

            {!isOnline && !issued && (
              <View className="flex-row items-center gap-2 rounded-2xl border border-amber-200 bg-amber-50 p-3">
                <Icon name="cloud-offline" size={18} color="#B45309" />
                <Text variant="caption" color="secondary" style={{ flex: 1 }}>
                  You're offline — the certificate is saved on this device and syncs automatically.
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
          <Button title="Re-dictate" variant="outline" onPress={() => setCapturing(true)} />
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
