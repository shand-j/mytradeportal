import { useRouter } from "expo-router";
import { CertificatesScreen } from "../../src/screens/trade/CertificatesScreen";

export default function CertificatesRoute() {
  const router = useRouter();
  return (
    <CertificatesScreen
      onBack={() => router.back()}
      onOpen={(id) => router.push(`/(trade)/certificate/${id}`)}
      onNew={() => router.push("/(trade)/certificate/new")}
    />
  );
}
