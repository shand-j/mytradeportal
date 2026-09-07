import { useMemo, useState } from "react";
import { Linking, ScrollView, View } from "react-native";
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

function ExternalContact({ lead, onClose }: { lead: Lead; onClose: () => void }) {
  const [sent, setSent] = useState(false);
  const channel = lead.preferredChannel ?? "sms";
  const phone = lead.customerPhone ?? "";
  const message = encodeURIComponent(
    `Hi ${lead.customerName}, it's ${lead.title.toLowerCase()}. Could I grab a bit more info before quoting?`
  );

  const openSms = async () => {
    const url = `sms:${phone.replace(/\s/g, "")}?body=${message}`;
    const can = await Linking.canOpenURL(url);
    if (can) await Linking.openURL(url);
    setSent(true);
  };

  const openWhatsApp = async () => {
    const cleaned = phone.replace(/\D/g, "").replace(/^0/, "44");
    const url = `https://wa.me/${cleaned}?text=${message}`;
    const can = await Linking.canOpenURL(url);
    if (can) await Linking.openURL(url);
    setSent(true);
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
          {lead.preferredChannel ? "Customer preference" : "Choose a channel"}
        </Text>
        <Text variant="body" color="secondary">
          {lead.preferredChannel
            ? `This customer normally contacts you via ${channel.toUpperCase()}.`
            : "This customer is not registered. Send your request by SMS or WhatsApp."}
        </Text>
      </View>

      <Button
        testID="request-info-sms"
        title="Send SMS request"
        variant={channel === "sms" ? "primary" : "outline"}
        onPress={openSms}
      />
      <Button
        testID="request-info-whatsapp"
        title="Open WhatsApp request"
        variant={channel === "whatsapp" ? "primary" : "outline"}
        onPress={openWhatsApp}
      />

      {sent && (
        <View className="rounded-2xl bg-green-100 p-4">
          <Text variant="body" color="secondary" align="center">
            Handoff opened. In a real build this would launch your messaging app with a pre-filled
            request.
          </Text>
        </View>
      )}
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
        <ExternalContact lead={lead} onClose={onClose} />
      )}
    </Screen>
  );
}
