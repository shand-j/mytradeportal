import { useLocalSearchParams, useRouter } from "expo-router";
import { CertificateScreen } from "../../../src/screens/trade/CertificateScreen";
import { MOCK_CERTIFICATES } from "../../../src/data/mockCertificates";

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

  const certificate = MOCK_CERTIFICATES.find((c) => c.id === id);
  if (!certificate) return null;

  return <CertificateScreen certificate={certificate} onClose={back} />;
}
