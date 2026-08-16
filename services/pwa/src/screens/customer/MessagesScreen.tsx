import { useEffect, useMemo, useRef, useState } from "react";
import { Pressable, ScrollView, TextInput, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { useBusiness } from "../../theme/ThemeProvider";

type Message = {
  id: string;
  sender: "business" | "customer";
  text: string;
  timestamp: string;
};

const INITIAL_MESSAGES: Message[] = [
  {
    id: "m1",
    sender: "business",
    text: "Hi Jane, thanks for your consumer unit upgrade request. I've reviewed the details and your quote is ready.",
    timestamp: "09:00",
  },
  {
    id: "m2",
    sender: "customer",
    text: "Great, thanks. Can you confirm how long the work takes?",
    timestamp: "09:15",
  },
  {
    id: "m3",
    sender: "business",
    text: "Usually 4-6 hours. I've sent the full quote through — take a look and let me know if you'd like any changes.",
    timestamp: "09:16",
  },
];

export type MessagesScreenProps = {
  initialComposerText?: string;
};

export function MessagesScreen({ initialComposerText }: MessagesScreenProps) {
  const { business } = useBusiness();
  const [messages, setMessages] = useState<Message[]>(INITIAL_MESSAGES);
  const [text, setText] = useState(initialComposerText ?? "");
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    if (initialComposerText) {
      setText(initialComposerText);
    }
  }, [initialComposerText]);

  const send = () => {
    const trimmed = text.trim();
    if (!trimmed) return;

    setMessages((prev) => [
      ...prev,
      {
        id: `msg-${Date.now()}`,
        sender: "customer",
        text: trimmed,
        timestamp: "Now",
      },
    ]);
    setText("");
  };

  return (
    <Screen>
      <Header title={`Messages · ${business?.name ?? "Your electrician"}`} />

      <ScrollView
        ref={scrollRef}
        className="flex-1"
        contentContainerStyle={{ gap: 12, paddingBottom: 16 }}
        onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}
      >
        <View className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
          <Text variant="caption" color="secondary" align="center">
            Messages with {business?.name ?? "your electrician"} about your quotes and bookings.
          </Text>
        </View>

        {messages.map((message) => (
          <View
            key={message.id}
            className={`flex-row ${message.sender === "customer" ? "justify-end" : "justify-start"}`}
          >
            <View className="max-w-[80%] gap-1">
              <View
                className="rounded-2xl px-4 py-3"
                style={{
                  backgroundColor: message.sender === "customer" ? "#2563EB" : "#F3F4F6",
                }}
              >
                <Text
                  variant="body"
                  style={{ color: message.sender === "customer" ? "#FFFFFF" : "#111827" }}
                >
                  {message.text}
                </Text>
              </View>
              <Text
                variant="caption"
                color="secondary"
                align={message.sender === "customer" ? "right" : "left"}
              >
                {message.timestamp}
              </Text>
            </View>
          </View>
        ))}
      </ScrollView>

      <View className="flex-row items-center gap-2 border-t border-slate-200 bg-white pt-3">
        <TextInput
          className="h-12 flex-1 rounded-xl border border-slate-200 bg-slate-50 px-4 text-base text-slate-900"
          value={text}
          onChangeText={setText}
          placeholder="Type a message…"
          placeholderTextColor="#94A3B8"
          multiline
          maxLength={500}
          returnKeyType="send"
          onSubmitEditing={send}
          blurOnSubmit={false}
        />
        <Button title="Send" size="sm" onPress={send} disabled={!text.trim()} />
      </View>
    </Screen>
  );
}
