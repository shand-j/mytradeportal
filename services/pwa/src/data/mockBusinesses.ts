import { BusinessConfig } from "../types";

export const MOCK_BUSINESSES: Record<string, BusinessConfig> = {
  demo: {
    slug: "demo",
    code: "123456",
    name: "Demo Electrical Ltd",
    primaryColor: "#2563EB",
    secondaryColor: "#1D4ED8",
    logoUrl: undefined,
    businessServices: [
      "ev_charger",
      "consumer_unit",
      "full_rewire",
      "eicr",
      "additional_points",
      "outdoor_power",
      "fault_finding",
      "emergency_callout",
    ],
    contactPhone: "0800 123 4567",
    address: "123 Trade Street, London, E1 6AN",
  },
  jenkins: {
    slug: "jenkins",
    code: "654321",
    name: "Jenkins Electrical",
    primaryColor: "#D4650A",
    secondaryColor: "#7C3AED",
    logoUrl: undefined,
    businessServices: [
      "consumer_unit",
      "full_rewire",
      "eicr",
      "additional_points",
      "lighting_design",
      "emergency_callout",
    ],
    contactPhone: "0800 987 6543",
    address: "45 Spark Avenue, Manchester, M1 2AB",
  },
};

export function lookupMockBusiness(code: string): BusinessConfig | null {
  const normalised = code.trim();
  return (
    Object.values(MOCK_BUSINESSES).find(
      (b) => b.code === normalised || b.slug === normalised.toLowerCase()
    ) ?? null
  );
}
