import { Ionicons } from "@expo/vector-icons";

export type IconName =
  | "dashboard"
  | "quotes"
  | "customers"
  | "calendar"
  | "settings"
  | "more"
  | "back"
  | "requests"
  | "messages"
  | "profile"
  | "image"
  | "video"
  | "add"
  | "close"
  | "checkmark"
  | "search"
  | "phone"
  | "message"
  | "sms"
  | "navigate"
  | "plus"
  | "info"
  | "car"
  | "hardware"
  | "flash"
  | "document"
  | "power"
  | "sunny"
  | "warning"
  | "help"
  | "whatsapp";

const ICONS: Record<IconName, keyof typeof Ionicons.glyphMap> = {
  dashboard: "home",
  quotes: "document-text",
  customers: "people",
  calendar: "calendar",
  settings: "settings",
  more: "ellipsis-vertical",
  back: "arrow-back",
  requests: "document-text",
  messages: "chatbubble",
  profile: "person",
  image: "image",
  video: "videocam",
  add: "add",
  close: "close",
  checkmark: "checkmark",
  search: "search",
  phone: "call",
  message: "chatbubble",
  sms: "mail",
  navigate: "navigate",
  plus: "add",
  info: "information-circle",
  car: "car",
  hardware: "hardware-chip",
  flash: "flash",
  document: "document-text",
  power: "power",
  sunny: "sunny",
  warning: "warning",
  help: "help-circle",
  whatsapp: "logo-whatsapp",
};

export function Icon({
  name,
  size = 22,
  color = "#111827",
}: {
  name: IconName;
  size?: number;
  color?: string;
}) {
  return <Ionicons name={ICONS[name]} size={size} color={color} />;
}
