/**
 * Electrical-trade vocabulary hints for on-device speech recognition
 * (`contextualStrings` on SFSpeechRecognitionRequest). Brands and categories
 * are seeded from the cost-item catalogue (services/api/scripts/seed_cost_items.py);
 * the rest is a curated list of UK domestic electrical jargon.
 */
export const VOICE_CONTEXTUAL_STRINGS: string[] = [
  // Circuit protection & consumer units
  "consumer unit",
  "fuse board",
  "RCBO",
  "RCD",
  "MCB",
  "SPD",
  "surge protection",
  "main switch",
  "high integrity",
  // Brands from the cost-item catalogue
  "FuseBox",
  "Lewden",
  "British General",
  "MK",
  "Prysmian",
  "Rolec",
  "Zappi",
  "Varilight",
  "FireAngel",
  "D-Line",
  "Wylex",
  "Hager",
  // Wiring & containment
  "twin and earth",
  "armoured cable",
  "SWA",
  "6mm cable",
  "10mm cable",
  "2.5mm",
  "conduit",
  "trunking",
  "junction box",
  // Earthing & bonding
  "earthing",
  "bonding",
  "earth electrode",
  "main earth",
  // Accessories & fittings
  "sockets",
  "socket outlet",
  "spur",
  "fused spur",
  "downlights",
  "lighting circuit",
  "dimmer switch",
  "cooker circuit",
  "shower circuit",
  "EV charger",
  // Certification & regs
  "EICR",
  "Part P",
  "BS 7671",
  "18th Edition",
  "minor works certificate",
  "electrical installation certificate",
  // Common job phrases
  "rewire",
  "full rewire",
  "first fix",
  "second fix",
  "fault finding",
  "tripping",
  "nuisance tripping",
];
