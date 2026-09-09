import { useRouter } from "expo-router";
import { JobCreateScreen } from "../../../src/screens/trade/JobCreateScreen";

export default function JobCreateRoute() {
  const router = useRouter();
  return <JobCreateScreen onClose={() => router.back()} />;
}
