import { useMemo } from "react";
import { ScrollView, View } from "react-native";
import { useRouter } from "expo-router";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { ChatThread } from "../customer/MessagesScreen";
import { Lead, Quote } from "../../types";

export type RequestInfoScreenProps = {
  lead: Lead;
  quote?: Quote | null;
  onClose: () => void;
};

function ExternalContact({ lead }: { lead: Lead }) {
  const router = useRouter();
  const phone = lead.customerPhone ?? "";

  const openChat = () => {
    router.push({ pathname: "/(trade)/messages", params: { quoteRequestId: lead.id } });
  };

  return (
    <ScrollView className="flex-1" contentContainerClassName="gap-4 pb-4">
      <View className="rounded-2xl bg-slate-100 p-4 gap-1">
        <Text variant="body" weight="semibold">
          {lead.customerName}
        </Text>
        <Text variant="caption" color="secondary">
          {phone || "No phone number"} · Not registered on the app
        </Text>
      </View>

      <View className="rounded-2xl bg-slate-100 p-4 gap-2">
        <Text variant="body" weight="semibold">
          Ask for more info
        </Text>
        <Text variant="body" color="secondary">
          Message this customer in an online chat thread. They are notified by email and
          can reply in the app.
        </Text>
      </View>

      <Button testID="request-info-chat" title="Message customer" onPress={openChat} />
    </ScrollView>
  );
}

export function RequestInfoScreen({ lead, quote, onClose }: RequestInfoScreenProps) {
  const isRegistered = lead.source === "app";
  const title = useMemo(
    () => (quote ? `Request info: ${quote.title}` : `Request info: ${lead.title}`),
    [quote, lead]
  );

  return (
    <Screen>
      <Header title={isRegistered ? "In-app chat" : "Contact customer"} onBack={onClose} />

      {isRegistered ? (
        <>
          <View className="mb-3 rounded-2xl bg-slate-100 p-4 gap-1">
            <Text variant="body" weight="semibold">
              {lead.customerName}
            </Text>
            <Text variant="caption" color="secondary">
              {lead.title}
            </Text>
            {lead.note ? (
              <Text variant="caption" color="secondary">
                {lead.note}
              </Text>
            ) : null}
          </View>
          <ChatThread
            quoteRequestId={lead.id}
            senderRole="business"
            hideBanner
          />
        </>
      ) : (
        <ExternalContact lead={lead} />
      )}
    </Screen>
  );
}
