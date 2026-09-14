import { useEffect, useMemo, useRef, useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, TextInput, View } from "react-native";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/ui/Header";
import { Icon } from "../../components/ui/Icon";
import { Screen } from "../../components/ui/Screen";
import { Text } from "../../components/ui/Text";
import { useBusiness } from "../../theme/ThemeProvider";
import { ChatMessage, ChatSenderRole, useCommunications } from "../../api/communications";
import { ApiError } from "../../lib/apiClient";
import {
  ContactCustomerCard,
  ContactCustomerCardProps,
} from "../../components/trade/ContactCustomerCard";

const clock = () => new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

/**
 * Module-level guard so the thread-open AI follow-up can never fire twice for
 * the same quote request — even under React 18 StrictMode double-effects or
 * remounts within the same app session.
 */
const followupTriggeredFor = new Set<string>();

function toDisplayMessages(
  messages: ChatMessage[],
  viewerRole: ChatSenderRole
): Array<{ id: string; sender: ChatSenderRole | "agent"; text: string; timestamp: string }> {
  return messages.map((m) => ({
    id: m.id,
    sender: m.senderRole === "ai" ? "agent" : m.senderRole,
    text: m.body,
    timestamp: m.createdAt
      ? new Date(m.createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      : clock(),
  }));
}

export type ChatThreadProps = {
  quoteRequestId?: string;
  senderRole?: ChatSenderRole;
  initialComposerText?: string;
  /** Hide the assistant info banner (useful when embedded inside another screen). */
  hideBanner?: boolean;
  /**
   * Set (business side only) when the customer cannot receive in-app chat:
   * the composer is replaced with a phone/email contact card. Existing thread
   * history still renders above it.
   */
  unreachableCustomer?: ContactCustomerCardProps;
};

/** The chat thread UI without a surrounding Screen/Header. */
export function ChatThread({
  quoteRequestId,
  senderRole = "customer",
  initialComposerText,
  hideBanner = false,
  unreachableCustomer,
}: ChatThreadProps) {
  const { business } = useBusiness();
  const businessName = business?.name ?? "Your electrician";
  const assistantName = `${businessName} Assistant`;

  const {
    messages: realMessages,
    isConnected,
    isLoading,
    error,
    sendMessage,
    isSending,
    generateAiFollowup,
  } = useCommunications(quoteRequestId, senderRole);

  const [text, setText] = useState(initialComposerText ?? "");
  const scrollRef = useRef<ScrollView>(null);
  const followupTriggered = useRef(false);
  // Local typing state, cleared in a finally so it cannot stick when the
  // follow-up errors or the mutation observer is remounted mid-flight.
  const [typing, setTyping] = useState(false);

  const runFollowup = async () => {
    setTyping(true);
    try {
      await generateAiFollowup();
    } catch {
      // Ignore failures: the user can still reply and the electrician sees the
      // original request.
    } finally {
      setTyping(false);
    }
  };

  const displayMessages = toDisplayMessages(realMessages, senderRole);

  // Trigger the AI follow-up once when the connected thread opens and no AI
  // message exists yet. This triage assistant exists to elicit details from
  // the customer, so it only fires on the customer side — when the business
  // opens the thread ("Request more info") it must never fire a slow LLM call
  // or show a bare typing indicator on an empty thread.
  useEffect(() => {
    if (senderRole !== "customer") return;
    if (!isConnected || !quoteRequestId || followupTriggered.current) return;
    if (followupTriggeredFor.has(quoteRequestId)) return;
    const lastMessage = realMessages[realMessages.length - 1];
    if (lastMessage && lastMessage.senderRole === "ai") return;
    if (realMessages.some((m) => m.senderRole === "ai")) return;

    followupTriggered.current = true;
    followupTriggeredFor.add(quoteRequestId);
    void runFollowup();
  }, [senderRole, isConnected, quoteRequestId, realMessages]);

  const handleSend = async (override?: unknown) => {
    // onSubmitEditing/onPress pass an event, quick-reply chips pass a string.
    const trimmed = (typeof override === "string" ? override : text).trim();
    if (!trimmed) return;
    if (typeof override !== "string") setText("");

    if (isConnected && quoteRequestId) {
      await sendMessage(trimmed);

      // After a customer reply, ask the AI for the next turn. The backend may
      // return another clarifying question or, once it is >80% confident, a
      // thank-you closure. If the previous AI message was already a closure,
      // don't keep the conversation looping. Business messages never prompt
      // the AI, and a follow-up failure must not break the send.
      if (senderRole !== "customer") return;
      const lastAi = [...realMessages]
        .reverse()
        .find((m) => m.senderRole === "ai");
      if (!lastAi?.aiMetadata?.complete) {
        await runFollowup();
      }
    }
  };

  const bubbleFor = (sender: ChatSenderRole | "agent") => {
    if (sender === "customer" || sender === "business") return { bg: "#0F1E26", fg: "#FFFFFF" };
    if (sender === "agent" || sender === "ai") return { bg: "#FEF9E8", fg: "#111827" };
    return { bg: "#F3F4F6", fg: "#111827" };
  };

  const isOutgoing = (sender: ChatSenderRole | "agent") =>
    (senderRole === "customer" && sender === "customer") ||
    (senderRole === "business" && sender === "business");

  const isNetworkError = error instanceof Error && error.name === "NetworkError";
  // A 404 means the thread itself is gone (deleted lead or a stale chat link
  // from an old notification). That is an empty inbox, not a failure — show
  // the empty state instead of an error banner; the composer stays disabled
  // because the query never succeeded.
  const isMissingThread = error instanceof ApiError && error.status === 404;
  const threadError = error && !isMissingThread ? error : null;

  // Quick-reply chips from the latest AI message. Only shown while that AI
  // message is still the last in the thread — once the customer replies, the
  // choices are stale. Customer side only.
  const lastThreadMessage = realMessages[realMessages.length - 1];
  const quickReplies =
    senderRole === "customer" && lastThreadMessage?.senderRole === "ai"
      ? (lastThreadMessage.aiMetadata?.options ?? []).filter(
          (option) => typeof option === "string" && option.trim().length > 0
        )
      : [];

  return (
    <KeyboardAvoidingView
      style={{ flex: 1 }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        ref={scrollRef}
        className="flex-1"
        contentContainerStyle={{ gap: 12, paddingBottom: 16 }}
        onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}
        keyboardShouldPersistTaps="handled"
      >
        {!hideBanner && (
          <View className="flex-row items-center gap-2 rounded-2xl border border-accent-200 bg-accent-50 p-3">
            <Icon name="sparkles" size={18} color="#B27E00" />
            <Text variant="caption" color="secondary" style={{ flex: 1 }}>
              {assistantName} helps refine your request so your quote is accurate.
            </Text>
          </View>
        )}

        {!!threadError && (
          <View className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
            <Text variant="caption" color="warning" align="center">
              {isNetworkError
                ? "Connect to the internet to view and send messages."
                : "Could not load messages. Please try again."}
            </Text>
          </View>
        )}

        {isLoading && (
          <Text testID="chat-loading" variant="caption" color="secondary" align="center">
            Loading messages…
          </Text>
        )}

        {!isLoading && !threadError && displayMessages.length === 0 && !typing && (
          <View className="rounded-2xl bg-slate-100 p-4">
            <Text variant="caption" color="secondary" align="center">
              {unreachableCustomer
                ? "No messages yet — this customer can't receive in-app chat."
                : "No messages yet — start the conversation below."}
            </Text>
          </View>
        )}

        {displayMessages.map((message) => {
          const { bg, fg } = bubbleFor(message.sender);
          const outgoing = isOutgoing(message.sender);
          const isAgent = message.sender === "agent" || message.sender === "ai";
          return (
            <View
              key={message.id}
              testID={`chat-message-${message.sender}`}
              className={`flex-row ${outgoing ? "justify-end" : "justify-start"}`}
            >
              <View className="max-w-[82%] gap-1">
                {isAgent && (
                  <View className="flex-row items-center gap-1">
                    <Icon name="sparkles" size={12} color="#B27E00" />
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
                <Text variant="caption" color="secondary" align={outgoing ? "right" : "left"}>
                  {message.timestamp}
                </Text>
              </View>
            </View>
          );
        })}

        {typing && (
          <View className="flex-row justify-start">
            <View className="rounded-2xl bg-accent-50 px-4 py-3">
              <Text variant="body" color="secondary" testID="chat-typing">
                {assistantName} is typing…
              </Text>
            </View>
          </View>
        )}
      </ScrollView>

      {quickReplies.length > 0 && (
        <View className="flex-row flex-wrap gap-2 border-t border-slate-200 bg-white pt-3">
          {quickReplies.map((option, index) => (
            <Pressable
              key={option}
              testID={`chat-quick-reply-${index}`}
              disabled={isSending || !isConnected}
              onPress={() => void handleSend(option)}
            >
              <View className="rounded-full border border-accent-200 bg-accent-50 px-3 py-1.5">
                <Text variant="caption" color="secondary">
                  {option}
                </Text>
              </View>
            </Pressable>
          ))}
        </View>
      )}

      {unreachableCustomer ? (
        <View className="border-t border-slate-200 pt-3">
          <ContactCustomerCard {...unreachableCustomer} />
        </View>
      ) : (
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
            onSubmitEditing={handleSend}
            blurOnSubmit={false}
          />
          <Button
            testID="chat-send"
            title="Send"
            size="sm"
            onPress={handleSend}
            disabled={!text.trim() || isSending || isLoading || !isConnected}
          />
        </View>
      )}
    </KeyboardAvoidingView>
  );
}

export type MessagesScreenProps = ChatThreadProps & {
  onBack?: () => void;
};

export function MessagesScreen({ quoteRequestId, senderRole, initialComposerText, unreachableCustomer, onBack }: MessagesScreenProps) {
  const { business } = useBusiness();
  const businessName = business?.name ?? "Your electrician";

  return (
    <Screen>
      <Header
        title="Messages"
        onBack={onBack}
        rightAction={
          <View className="flex-row items-center gap-1">
            <Icon name="sparkles" size={16} color="#B27E00" />
            <Text variant="caption" color="secondary">
              AI
            </Text>
          </View>
        }
      />

      <ChatThread
        quoteRequestId={quoteRequestId}
        senderRole={senderRole}
        initialComposerText={initialComposerText}
        unreachableCustomer={unreachableCustomer}
      />
    </Screen>
  );
}
