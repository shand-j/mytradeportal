import { useMemo } from "react";
import { View } from "react-native";
import { generateQrMatrix } from "../../lib/qr";

export type QrCodeProps = {
  value: string;
  /** Rendered width/height in dp (includes the 4-module quiet zone). */
  size?: number;
  color?: string;
  backgroundColor?: string;
  testID?: string;
};

/**
 * Renders a QR code with plain Views — dependency-free and OTA-safe (no
 * react-native-svg / native modules). Consecutive dark modules in a row are
 * merged into a single View to keep the view count low.
 */
export function QrCode({
  value,
  size = 200,
  color = "#0F1E26",
  backgroundColor = "#FFFFFF",
  testID,
}: QrCodeProps) {
  const matrix = useMemo(() => generateQrMatrix(value), [value]);
  const moduleCount = matrix.length;
  // 4-module quiet zone on every side, per the QR spec.
  const cell = size / (moduleCount + 8);

  return (
    <View
      testID={testID}
      accessibilityLabel={`QR code for ${value}`}
      style={{
        width: size,
        height: size,
        backgroundColor,
        padding: cell * 4,
        borderRadius: 12,
      }}
    >
      {matrix.map((row, y) => {
        // Merge consecutive dark modules into runs: [start, endExclusive].
        const runs: [number, number][] = [];
        for (let x = 0; x < moduleCount; x++) {
          if (!row[x]) continue;
          const last = runs[runs.length - 1];
          if (last && last[1] === x) {
            last[1] = x + 1;
          } else {
            runs.push([x, x + 1]);
          }
        }
        let prevEnd = 0;
        return (
          <View key={y} style={{ flexDirection: "row", height: cell }}>
            {runs.map(([start, end]) => {
              const gap = start - prevEnd;
              prevEnd = end;
              return (
                <View
                  key={start}
                  style={{
                    marginLeft: gap * cell,
                    width: (end - start) * cell,
                    height: cell,
                    backgroundColor: color,
                  }}
                />
              );
            })}
          </View>
        );
      })}
    </View>
  );
}
