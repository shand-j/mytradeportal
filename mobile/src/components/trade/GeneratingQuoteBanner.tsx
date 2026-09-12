import { Pressable, View } from "react-native";
import { useRouter } from "expo-router";
import { Icon } from "../ui/Icon";
import { Text } from "../ui/Text";
import { useQuoteGenerationStore } from "../../stores/quoteGenerationStore";

/**
 * Persistent banner on the quotes/leads list tracking an async AI quote
 * generation: "generating" while the backend job runs, "ready" once the
 * quote_ready notification arrives (tap to open the quote), "failed" on
 * quote_failed. Dismissible at any point.
 */
export function GeneratingQuoteBanner() {
  const router = useRouter();
  const { phase, readyQuoteId, dismissed, dismiss, reset } = useQuoteGenerationStore();

  if (!phase || dismissed) return null;

  if (phase === "ready") {
    return (
      <Pressable
        testID="quote-ready-banner"
        onPress={() => {
          reset();
          if (readyQuoteId) {
            router.push(`/(trade)/quote/${readyQuoteId}`);
          }
        }}
      >
        <View className="flex-row items-center gap-3 rounded-2xl border border-success-200 bg-success-50 p-4">
          <View className="h-9 w-9 items-center justify-center rounded-full bg-primary">
            <Icon name="checkmark" size={18} color="#FFC107" />
          </View>
          <View className="flex-1">
            <Text variant="body" weight="semibold">
              Your AI quote is ready
            </Text>
            <Text variant="caption" color="secondary">
              Tap to review and send it
            </Text>
          </View>
          <Pressable
            testID="quote-ready-dismiss"
            onPress={reset}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
            accessibilityLabel="Dismiss"
          >
            <Icon name="close" size={18} color="#6B7280" />
          </Pressable>
        </View>
      </Pressable>
    );
  }

  if (phase === "failed") {
    return (
      <View className="flex-row items-center gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4">
        <View className="h-9 w-9 items-center justify-center rounded-full bg-amber-500">
          <Icon name="warning" size={18} color="#FFFFFF" />
        </View>
        <View className="flex-1">
          <Text variant="body" weight="semibold">
            Quote generation failed
          </Text>
          <Text variant="caption" color="secondary">
            Please try again, or build the quote manually.
          </Text>
        </View>
        <Pressable
          testID="quote-generating-dismiss"
          onPress={reset}
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          accessibilityLabel="Dismiss"
        >
          <Icon name="close" size={18} color="#6B7280" />
        </Pressable>
      </View>
    );
  }

  return (
    <View
      testID="quote-generating-banner"
      className="flex-row items-center gap-3 rounded-2xl border border-primary-200 bg-primary-50 p-4"
    >
      <View className="h-9 w-9 items-center justify-center rounded-full bg-primary">
        <Icon name="sparkles" size={18} color="#FFC107" />
      </View>
      <View className="flex-1">
        <Text variant="body" weight="semibold">
          Quote is generating
        </Text>
        <Text variant="caption" color="secondary">
          You'll be notified when it's ready for review.
        </Text>
      </View>
      <Pressable
        testID="quote-generating-dismiss"
        onPress={dismiss}
        hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        accessibilityLabel="Dismiss"
      >
        <Icon name="close" size={18} color="#6B7280" />
      </Pressable>
    </View>
  );
}
