import { useEffect, useRef, useState } from "react";
import { Animated, Easing, Pressable, View } from "react-native";
import { Button } from "./ui/Button";
import { Icon } from "./ui/Icon";
import { Text } from "./ui/Text";

type Phase = "idle" | "listening" | "processing";

export type VoiceCaptureSheetProps = {
  /** Heading, e.g. "Dictate a quote" or "Dictate test results". */
  title: string;
  /** Helper prompt shown before recording, e.g. "Describe the job out loud." */
  prompt: string;
  /** The transcript that streams in word-by-word while "listening". */
  transcript: string;
  /** Label for the confirm button once analysed. */
  confirmLabel: string;
  onComplete: (transcript: string) => void;
  onCancel: () => void;
};

const BAR_COUNT = 5;

function WaveBar({ index, active }: { index: number; active: boolean }) {
  const v = useRef(new Animated.Value(0.25)).current;

  useEffect(() => {
    if (active) {
      const loop = Animated.loop(
        Animated.sequence([
          Animated.timing(v, {
            toValue: 1,
            duration: 420 + index * 90,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: false,
          }),
          Animated.timing(v, {
            toValue: 0.25,
            duration: 420 + index * 90,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: false,
          }),
        ])
      );
      loop.start();
      return () => loop.stop();
    }
    v.setValue(0.25);
  }, [active, index, v]);

  const height = v.interpolate({ inputRange: [0, 1], outputRange: [12, 56] });

  return (
    <Animated.View
      style={{ width: 8, borderRadius: 4, backgroundColor: "#FFFFFF", opacity: 0.95, height }}
    />
  );
}

export function VoiceCaptureSheet({
  title,
  prompt,
  transcript,
  confirmLabel,
  onComplete,
  onCancel,
}: VoiceCaptureSheetProps) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [shown, setShown] = useState("");
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  const clearTimers = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  };
  useEffect(() => () => clearTimers(), []);

  const words = transcript.split(" ");

  const startListening = () => {
    setPhase("listening");
    setShown("");
    // Stream the transcript word-by-word for a realistic dictation feel.
    words.forEach((_, i) => {
      const t = setTimeout(() => {
        setShown(words.slice(0, i + 1).join(" "));
        if (i === words.length - 1) {
          const done = setTimeout(() => finishListening(), 900);
          timers.current.push(done);
        }
      }, 260 * (i + 1));
      timers.current.push(t);
    });
  };

  const finishListening = () => {
    clearTimers();
    setShown(transcript);
    setPhase("processing");
    const t = setTimeout(() => onComplete(transcript), 1900);
    timers.current.push(t);
  };

  return (
    <View className="flex-1 bg-slate-900" testID="voice-sheet">
      {/* Header */}
      <View
        className="flex-row items-center justify-between px-5"
        style={{ paddingTop: 16, paddingBottom: 8 }}
      >
        <Pressable testID="voice-cancel" onPress={onCancel} hitSlop={8} className="py-1 pr-2">
          <Text variant="body" weight="medium" style={{ color: "#E5E7EB" }}>
            Cancel
          </Text>
        </Pressable>
        <Text variant="subtitle" weight="bold" style={{ color: "#FFFFFF", fontSize: 18 }}>
          {title}
        </Text>
        <View style={{ width: 60 }} />
      </View>

      {/* Body */}
      <View className="flex-1 items-center justify-center px-6 gap-8">
        <View className="items-center gap-2">
          <View className="flex-row items-center gap-1">
            <Icon name="sparkles" size={16} color="#A5B4FC" />
            <Text variant="caption" style={{ color: "#A5B4FC" }}>
              On-device voice · AI drafting
            </Text>
          </View>
          <Text variant="body" align="center" style={{ color: "#CBD5E1" }}>
            {phase === "idle"
              ? prompt
              : phase === "listening"
                ? "Listening…"
                : "Analysing with AI…"}
          </Text>
        </View>

        {/* Mic + waveform */}
        <View className="items-center justify-center" style={{ height: 160 }}>
          <View
            className="items-center justify-center rounded-full"
            style={{
              width: 128,
              height: 128,
              backgroundColor:
                phase === "listening" ? "#2563EB" : phase === "processing" ? "#4F46E5" : "#1E293B",
              borderWidth: 2,
              borderColor: phase === "idle" ? "#334155" : "#60A5FA",
            }}
          >
            {phase === "listening" ? (
              <View className="flex-row items-end gap-1.5" style={{ height: 56 }}>
                {Array.from({ length: BAR_COUNT }).map((_, i) => (
                  <WaveBar key={i} index={i} active />
                ))}
              </View>
            ) : (
              <Icon name={phase === "processing" ? "sparkles" : "mic"} size={52} color="#FFFFFF" />
            )}
          </View>
        </View>

        {/* Transcript */}
        {shown.length > 0 && (
          <View
            className="w-full rounded-2xl p-4"
            style={{ backgroundColor: "#0F172A", borderWidth: 1, borderColor: "#1E293B" }}
          >
            <Text variant="caption" style={{ color: "#64748B", marginBottom: 4 }}>
              Transcript
            </Text>
            <Text variant="body" style={{ color: "#F1F5F9" }} testID="voice-transcript">
              {shown}
              {phase === "listening" ? " ▋" : ""}
            </Text>
          </View>
        )}
      </View>

      {/* Footer */}
      <View className="px-5" style={{ paddingBottom: 28, gap: 12 }}>
        {phase === "idle" && (
          <Button testID="voice-start" title="Start dictation" onPress={startListening} />
        )}
        {phase === "listening" && (
          <Button testID="voice-stop" title="Stop & draft" onPress={finishListening} />
        )}
        {phase === "processing" && (
          <View className="items-center py-2">
            <Text variant="caption" style={{ color: "#94A3B8" }}>
              Extracting {confirmLabel.toLowerCase()}…
            </Text>
          </View>
        )}
      </View>
    </View>
  );
}
