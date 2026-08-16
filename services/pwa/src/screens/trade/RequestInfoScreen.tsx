import { useMemo, useState } from "react";
import { Linking, ScrollView, TextInput, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { Lead, Quote } from "../../types";

export type RequestInfoScreenProps = {
  lead: Lead;
  quote?: Quote | null;
  onClose: () => void;
};

type ChatMessage = {
  id: string;
  sender: "trade" | "customer";
  text: string;
  timestamp: string;
};

const PRESET_REQUESTS = [
  "Could you send a few photos of your current consumer unit?",
  "I'd like to book a site visit first. What days work for you?",
  "Do you know roughly when the property was built?",
  "Is there driveway access for a van?",
];

function useRegisteredChat(lead: Lead) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "m1",
      sender: "customer",
      text: `Hi, I submitted a request for ${lead.title.toLowerCase()} via the app.`,
      timestamp: "09:41",
    },
  ]);
  const [draft, setDraft] = useState("");

  const send = (text: string) => {
    if (!text.trim()) return;
    const tradeMsg: ChatMessage = {
      id: `t-${Date.now()}`,
      sender: "trade",
      text: text.trim(),
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };
    setMessages((prev) => [...prev, tradeMsg]);
    setDraft("");
  };

  return { messages, draft, setDraft, send };
}

function RegisteredChat({ lead, onClose }: { lead: Lead; onClose: () => void }) {
  const { messages, draft, setDraft, send } = useRegisteredChat(lead);

  return (
    <>
      <ScrollView className="flex-1" contentContainerClassName="gap-3 pb-4">
        <View className="rounded-2xl bg-slate-100 p-4 gap-1">
          <Text variant="body" weight="semibold">
            {lead.customerName}
          </Text>
          <Text variant="caption" color="secondary">
            Registered customer · In-app messaging
          </Text>
        </View>

        {messages.map((msg) => (
          <View
            key={msg.id}
            className={`max-w-[80%] rounded-2xl p-3 gap-1 ${
              msg.sender === "trade"
                ? "self-end rounded-br-sm bg-blue-600"
                : "self-start rounded-bl-sm bg-slate-100"
            }`}
          >
            <Text variant="body" style={{ color: msg.sender === "trade" ? "#FFFFFF" : "#111827" }}>
              {msg.text}
            </Text>
            <Text variant="caption" style={{ color: msg.sender === "trade" ? "#E5E7EB" : "#6B7280" }}>
              {msg.timestamp}
            </Text>
          </View>
        ))}

        <View className="mt-2 rounded-2xl border border-amber-200 bg-amber-50 p-4 gap-3">
          <Text variant="caption" color="secondary">
            Quick requests
          </Text>
          <View className="gap-2">
            {PRESET_REQUESTS.map((text) => (
              <Button key={text} title={text} variant="outline" size="sm" onPress={() => send(text)} />
            ))}
          </View>
        </View>
      </ScrollView>

      <View className="flex-row items-end gap-2 border-t border-slate-200 pt-3">
        <TextInput
          className="flex-1 max-h-[100px] rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-base text-slate-900"
          value={draft}
          onChangeText={setDraft}
          placeholder="Type a message…"
          multiline
        />
        <Button title="Send" onPress={() => send(draft)} />
      </View>
    </>
  );
}

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
        <RegisteredChat lead={lead} onClose={onClose} />
      ) : (
        <ExternalContact lead={lead} onClose={onClose} />
      )}
    </Screen>
  );
}
