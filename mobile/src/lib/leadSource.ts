import { Lead } from "../types";

export function getLeadSourceLabel(source: Lead["source"]): string {
  const labels: Record<Lead["source"], string> = {
    app: "Customer app",
    in_app: "Customer app",
    qr: "QR code",
    web: "Web form",
    web_form: "Web form",
    whatsapp: "WhatsApp",
    sms: "SMS",
    phone: "Phone",
    manual: "Manual",
  };
  return labels[source] ?? source;
}
