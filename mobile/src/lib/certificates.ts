import { CircuitTestRow } from "../types";

export function circuitPasses(row: CircuitTestRow): boolean {
  return row.zsMeasured <= row.zsMax && row.rcdTripMs <= 40 && row.ir >= 1;
}
