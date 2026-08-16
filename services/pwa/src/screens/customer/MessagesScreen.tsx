import { useEffect, useMemo, useRef, useState } from "react";
import { Pressable, ScrollView, TextInput, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Icon } from "../../components/ui/Icon";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { useBusiness } from "../../theme/ThemeProvider";

type Sender = "agent" | "business" | "customer";

type Message = {
  id: string;
  sender: Sender;
  text: string;
  timestamp: string;
};

// Scripted AI follow-up so the assistant can refine the quote in-app. Each turn
// shows an AI question with tappable suggested replies; the closing turn has no
// replies and confirms the quote is under way.
type FollowUpTurn = {
  question: string;
  replies: string[];
};

const FOLLOW_UP: FollowUpTurn[] = [
  {
    question: "How many circuits are on your current fuse board? A rough count is fine.",
    replies: ["Around 8", "Not sure"],
  },
  {
    question: "Is your current board modern RCD-protected, or older rewireable fuses?",
    replies: ["Older rewireable fuses", "Modern RCD", "Not sure"],
  },
  {
    question: "Any issues at the moment — no RCD protection, or occasional tripping?",
    replies: ["No RCD protection", "Occasional tripping", "No issues"],
  },
  {
    question: "Is the board easy to access, or is anything in front of it?",
    replies: ["Easy access in the garage", "A bit awkward"],
  },
  {
    question: "Great. Shall we include a full electrical safety check (EICR) with the upgrade?",
    replies: ["Yes please", "No thanks"],
  },
];

const clock = () => new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

export type MessagesScreenProps = {
  initialComposerText?: string;
  onBack?: () => void;
};

export function MessagesScreen({ initialComposerText, onBack }: MessagesScreenProps) {
  const { business } = useBusiness();
  const businessName = business?.name ?? "Your electrician";
  const assistantName = `${businessName} Assistant`;

  const [messages, setMessages] = useState<Message[]>([]);
  const [turnIndex, setTurnIndex] = useState(-1); // -1 = opening not sent yet
  const [typing, setTyping] = useState(true);
  const [text, setText] = useState(initialComposerText ?? "");
  const scrollRef = useRef<ScrollView>(null);

  const currentTurn = turnIndex >= 0 && turnIndex < FOLLOW_UP.length ? FOLLOW_UP[turnIndex] : null;
  const finished = turnIndex >= FOLLOW_UP.length;

  const pushAgent = (body: string) =>
    setMessages((prev) => [
      ...prev,
      { id: `a-${Date.now()}-${prev.length}`, sender: "agent", text: body, timestamp: clock() },
    ]);

  // Opening message + first question shortly after the screen mounts.
  useEffect(() => {
    const t1 = setTimeout(() => {
      pushAgent(
        `Hi there 👋 I'm ${businessName}'s AI assistant. I'm preparing your consumer unit upgrade quote — just a few quick questions to get it spot on.`
      );
    }, 700);
    const t2 = setTimeout(() => {
      setTyping(false);
      setTurnIndex(0);
      pushAgent(FOLLOW_UP[0].question);
    }, 1900);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const advance = (reply: string) => {
    setMessages((prev) => [
      ...prev,
      { id: `c-${Date.now()}`, sender: "customer", text: reply, timestamp: clock() },
    ]);
    const next = turnIndex + 1;
    setTyping(true);
    setTimeout(() => {
      setTyping(false);
      if (next < FOLLOW_UP.length) {
        setTurnIndex(next);
        pushAgent(FOLLOW_UP[next].question);
      } else {
        setTurnIndex(next);
        pushAgent(
          `Thanks — that's everything I need. I've added these details to your job and ${businessName} is preparing your quote now. You'll get it right here shortly. ✅`
        );
      }
    }, 1100);
  };

  const sendFreeText = () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    setText("");
    if (currentTurn) {
      advance(trimmed);
    } else {
      setMessages((prev) => [
        ...prev,
        { id: `c-${Date.now()}`, sender: "customer", text: trimmed, timestamp: clock() },
      ]);
    }
  };

  const bubbleFor = (sender: Sender) => {
    if (sender === "customer") return { bg: "#2563EB", fg: "#FFFFFF" };
    if (sender === "agent") return { bg: "#EEF2FF", fg: "#111827" };
    return { bg: "#F3F4F6", fg: "#111827" };
  };

  const showReplies = useMemo(
    () => Boolean(currentTurn) && !typing && !finished,
    [currentTurn, typing, finished]
  );

  return (
    <Screen>
      <Header
        title="Messages"
        onBack={onBack}
        rightAction={
          <View className="flex-row items-center gap-1">
            <Icon name="sparkles" size={16} color="#4F46E5" />
            <Text variant="caption" color="secondary">
              AI
            </Text>
          </View>
        }
      />

      <ScrollView
        ref={scrollRef}
        className="flex-1"
        contentContainerStyle={{ gap: 12, paddingBottom: 16 }}
        onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}
      >
        <View className="flex-row items-center gap-2 rounded-2xl border border-indigo-100 bg-indigo-50 p-3">
          <Icon name="sparkles" size={18} color="#4F46E5" />
          <Text variant="caption" color="secondary" style={{ flex: 1 }}>
            {assistantName} helps refine your request so your quote is accurate.
          </Text>
        </View>

        {messages.map((message) => {
          const { bg, fg } = bubbleFor(message.sender);
          const isCustomer = message.sender === "customer";
          return (
            <View
              key={message.id}
              className={`flex-row ${isCustomer ? "justify-end" : "justify-start"}`}
            >
              <View className="max-w-[82%] gap-1">
                {message.sender === "agent" && (
                  <View className="flex-row items-center gap-1">
                    <Icon name="sparkles" size={12} color="#4F46E5" />
                    <Text variant="caption" color="secondary" style={{ fontSize: 11 }}>
                      {assistantName}
                    </Text>
                  </View>
                )}
                <View className="rounded-2xl px-4 py-3" style={{ backgroundColor: bg }}>
                  <Text variant="body" style={{ color: fg }}>
                    {message.text}
                  </Text>
                </View>
                <Text variant="caption" color="secondary" align={isCustomer ? "right" : "left"}>
                  {message.timestamp}
                </Text>
              </View>
            </View>
          );
        })}

        {typing && (
          <View className="flex-row justify-start">
            <View className="rounded-2xl bg-indigo-50 px-4 py-3">
              <Text variant="body" color="secondary" testID="chat-typing">
                {assistantName} is typing…
              </Text>
            </View>
          </View>
        )}

        {showReplies && currentTurn && (
          <View className="flex-row flex-wrap justify-end gap-2">
            {currentTurn.replies.map((reply, index) => (
              <Pressable
                key={reply}
                testID={`chat-quick-reply-${index}`}
                onPress={() => advance(reply)}
                className="rounded-full border border-blue-200 bg-blue-50 px-4 py-2"
              >
                <Text variant="caption" color="primary" weight="semibold">
                  {reply}
                </Text>
              </Pressable>
            ))}
          </View>
        )}
      </ScrollView>

      <View className="flex-row items-center gap-2 border-t border-slate-200 bg-white pt-3">
        <TextInput
          testID="chat-composer"
          className="h-12 flex-1 rounded-xl border border-slate-200 bg-slate-50 px-4 text-base text-slate-900"
          value={text}
          onChangeText={setText}
          placeholder="Type a message…"
          placeholderTextColor="#94A3B8"
          multiline
          maxLength={500}
          returnKeyType="send"
          onSubmitEditing={sendFreeText}
          blurOnSubmit={false}
        />
        <Button
          testID="chat-send"
          title="Send"
          size="sm"
          onPress={sendFreeText}
          disabled={!text.trim()}
        />
      </View>
    </Screen>
  );
}
