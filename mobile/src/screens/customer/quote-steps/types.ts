import type { BusinessConfig } from "../../../types";

export type MediaItem = {
  id: string;
  label: string;
  type: "image" | "video";
};

export type ContactDetails = {
  name: string;
  mobile: string;
  email: string;
  preferredContact: "in_app_chat" | "phone" | "sms" | "whatsapp" | "email";
  bestTimeToCall: string[];
};

export type PropertyProfile = {
  type: string;
  age: string;
  bedrooms: number;
  receptions: number;
  floors: number;
  tenure: "owner" | "tenant" | "landlord" | "housing_assoc";
  flatAccess: boolean | null;
  parking: boolean | null;
  consumerUnitPhoto: string | null;
  fuseBoardStyle: string;
  knownIssues: string[];
};

export type BudgetContext = {
  budgetBand: string;
  howDidYouHear: string;
  insuranceClaim: boolean | null;
};

export type Consents = {
  termsPrivacy: boolean;
  contactPermission: boolean;
  marketingOptIn: boolean;
  landlordPermission: boolean;
};

export type TriageLevel = "emergency" | "priority" | "standard";

export type QuoteFormData = {
  postcode: string;
  inServiceArea: boolean | null;
  contact: ContactDetails;
  property: PropertyProfile;
  category: string;
  questionnaire: Record<string, unknown>;
  media: MediaItem[];
  urgency: string;
  preferredDates: string[];
  triage: TriageLevel;
  redFlagSymptoms: string[];
  budgetContext: BudgetContext;
  consents: Consents;
};

export const INITIAL_FORM_DATA: QuoteFormData = {
  postcode: "",
  inServiceArea: null,
  contact: {
    name: "",
    mobile: "",
    email: "",
    preferredContact: "in_app_chat",
    bestTimeToCall: [],
  },
  property: {
    type: "",
    age: "",
    bedrooms: 3,
    receptions: 2,
    floors: 2,
    tenure: "owner",
    flatAccess: null,
    parking: null,
    consumerUnitPhoto: null,
    fuseBoardStyle: "",
    knownIssues: [],
  },
  category: "",
  questionnaire: {},
  media: [],
  urgency: "flexible",
  preferredDates: [],
  triage: "standard",
  redFlagSymptoms: [],
  budgetContext: {
    budgetBand: "",
    howDidYouHear: "",
    insuranceClaim: null,
  },
  consents: {
    termsPrivacy: false,
    contactPermission: false,
    marketingOptIn: false,
    landlordPermission: false,
  },
};

export type StepComponentProps = {
  formData: QuoteFormData;
  updateFormData: (patch: Partial<QuoteFormData>) => void;
  onNext: () => void;
  onBack: () => void;
};

export type StepPropsWithBusiness = StepComponentProps & {
  business: BusinessConfig | null;
};

export const ALL_CATEGORIES = [
  { key: "ev_charger", label: "EV charger", icon: "car" as const },
  { key: "consumer_unit", label: "Consumer unit", icon: "hardware" as const },
  { key: "full_rewire", label: "Full rewire", icon: "flash" as const },
  { key: "eicr", label: "EICR", icon: "document" as const },
  { key: "additional_points", label: "Additional sockets", icon: "power" as const },
  { key: "outdoor_power", label: "Outdoor power", icon: "sunny" as const },
  { key: "fault_finding", label: "Fault finding", icon: "search" as const },
  { key: "emergency_callout", label: "Emergency callout", icon: "warning" as const },
  { key: "other", label: "Something else", icon: "help" as const },
];

export const RED_FLAG_SYMPTOMS = [
  "burning_smell",
  "smoke",
  "scorch",
  "shocks",
  "water",
  "partial_power_loss",
  "repeated_tripping",
];

export const RED_FLAG_EMERGENCY = [
  "burning_smell",
  "smoke",
  "scorch",
  "shocks",
  "water",
];

export function evaluateTriage(
  urgency: string,
  redFlagSymptoms: string[]
): TriageLevel {
  if (urgency === "emergency_today") return "emergency";
  if (redFlagSymptoms.some((s) => RED_FLAG_EMERGENCY.includes(s))) return "emergency";
  if (redFlagSymptoms.some((s) => RED_FLAG_SYMPTOMS.includes(s))) return "priority";
  return "standard";
}
