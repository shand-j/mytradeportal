import { useRouter } from "expo-router";
import { VoiceQuoteScreen } from "../../src/screens/trade/VoiceQuoteScreen";

export default function VoiceQuoteRoute() {
  const router = useRouter();
  return (
    <VoiceQuoteScreen
      onClose={() => router.back()}
      onCreated={(id) => router.replace(`/(trade)/quote/${id}`)}
    />
  );
}
