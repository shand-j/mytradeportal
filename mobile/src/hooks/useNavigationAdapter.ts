import { useRouter, usePathname } from "expo-router";

type NavigationParams = Record<string, unknown>;

const ROUTE_MAP: Record<string, (params?: NavigationParams) => string> = {
  Dashboard: () => "/(trade)/dashboard",
  Quotes: () => "/(trade)/quotes",
  Customers: () => "/(trade)/customers",
  Calendar: () => "/(trade)/calendar",
  Leads: () => "/(trade)/leads",
  Settings: () => "/(trade)/settings",
  Analytics: () => "/(trade)/analytics",
  Branding: () => "/(trade)/branding",
  "Follow-ups": () => "/(trade)/follow-ups",
  "Manual lead": () => "/(trade)/manual-lead",
  LeadDetail: (params) => `/(trade)/lead/${params?.id ?? ""}`,
  Quote: (params) => `/(trade)/quote/${params?.id ?? ""}`,
  QuoteIntake: (params) => `/(trade)/quote-intake?leadId=${params?.leadId ?? ""}`,
  RequestInfo: (params) => `/(trade)/request-info?leadId=${params?.leadId ?? ""}`,
  Job: (params) => `/(trade)/job/${params?.id ?? ""}`,
  Invoice: (params) => `/(trade)/invoice/${params?.id ?? ""}`,
  Requests: () => "/(customer)/requests",
  Messages: () => "/(customer)/messages",
  Profile: () => "/(customer)/profile",
  "Customer calendar": () => "/(customer)/calendar",
  Entry: () => "/",
};

export function useNavigationAdapter() {
  const router = useRouter();
  const pathname = usePathname();

  const navigate = (name: string, params?: NavigationParams) => {
    const pathFactory = ROUTE_MAP[name] ?? (() => `/${name.toLowerCase()}`);
    router.push(pathFactory(params));
  };

  const push = (name: string, params?: NavigationParams) => navigate(name, params);

  const goBack = () => {
    if (
      pathname === "/" ||
      pathname === "/(trade)/dashboard" ||
      pathname === "/(customer)/requests"
    ) {
      return;
    }
    router.back();
  };

  const setOptions = () => {
    // No-op. The custom tab bar handles visibility per screen.
  };

  return { navigate, push, goBack, setOptions };
}
