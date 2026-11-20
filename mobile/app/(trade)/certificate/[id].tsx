import { useLocalSearchParams, useRouter } from "expo-router";
import { CertificateScreen } from "../../../src/screens/trade/CertificateScreen";

export default function CertificateRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();

  const back = () => {
    if (router.canGoBack()) router.back();
    else router.replace("/(trade)/certificates");
  };

  if (id === "new") {
    return <CertificateScreen onClose={back} onIssued={() => back()} />;
  }

  // TODO: fetch existing certificate from backend once an API is available.
  return null;
}
