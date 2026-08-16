import { Certificate, CircuitTestRow } from "../types";

// Circuit schedule + test results that the voice dictation "fills in" for the
// new EICR. Zs-max values are illustrative BS 7671 max-Zs figures per device.
export const VOICE_EICR_CIRCUITS: CircuitTestRow[] = [
  { id: "c1", circuit: "Ring final — kitchen", protection: "32A Type B RCBO", zsMeasured: 0.82, zsMax: 1.09, rcdTripMs: 24, ir: 299 },
  { id: "c2", circuit: "Ring final — sockets ground floor", protection: "32A Type B RCBO", zsMeasured: 0.91, zsMax: 1.09, rcdTripMs: 27, ir: 299 },
  { id: "c3", circuit: "Lighting — ground floor", protection: "6A Type B RCBO", zsMeasured: 3.1, zsMax: 5.83, rcdTripMs: 22, ir: 299 },
  { id: "c4", circuit: "Cooker", protection: "32A Type B RCBO", zsMeasured: 0.68, zsMax: 1.09, rcdTripMs: 25, ir: 299 },
  { id: "c5", circuit: "Immersion heater", protection: "16A Type B RCBO", zsMeasured: 1.42, zsMax: 2.19, rcdTripMs: 29, ir: 299 },
];

export const MOCK_CERTIFICATES: Certificate[] = [
  {
    id: "cert-1",
    type: "EICR",
    customerName: "Alice Builder",
    address: "8 Old Mill Road, Manchester",
    postcode: "M1 2AB",
    status: "issued",
    overall: "satisfactory",
    circuits: [
      { id: "a1", circuit: "Ring final — sockets", protection: "32A Type B RCBO", zsMeasured: 0.88, zsMax: 1.09, rcdTripMs: 26, ir: 299 },
      { id: "a2", circuit: "Lighting", protection: "6A Type B RCBO", zsMeasured: 2.9, zsMax: 5.83, rcdTripMs: 23, ir: 299 },
    ],
    observations: [{ id: "o1", code: "C3", text: "No RCD label at consumer unit — improvement recommended." }],
    createdAt: new Date(Date.now() - 6 * 86400000).toISOString(),
    signedBy: "Demo Owner",
    signedAt: new Date(Date.now() - 6 * 86400000).toISOString(),
  },
];

export function circuitPasses(row: CircuitTestRow): boolean {
  return row.zsMeasured <= row.zsMax && row.rcdTripMs <= 40 && row.ir >= 1;
}
