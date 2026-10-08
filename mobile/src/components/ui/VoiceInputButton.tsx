import { useEffect, useRef, useState } from "react";
import { Animated, Platform, Pressable, StyleSheet, View } from "react-native";
import {
  ExpoSpeechRecognitionModule,
  useSpeechRecognitionEvent,
} from "expo-speech-recognition";
import { Icon } from "./Icon";
import { Text } from "./Text";
import { useTheme } from "../../theme/ThemeProvider";
import { VOICE_CONTEXTUAL_STRINGS } from "../../lib/voiceGlossary";

export type VoiceInputButtonProps = {
  /** Current field value — dictated text is appended to it. */
  value: string;
  onChangeText: (text: string) => void;
  testID?: string;
  disabled?: boolean;
};

/**
 * On-device dictation button (iOS SFSpeechRecognizer via expo-speech-recognition).
 * Tap to start: live partial transcription appends to the existing field text;
 * tap again (or ~3s of silence) to stop. Hidden on Android/web — the web e2e
 * bundle must not touch the native module's recognition flow.
 */
export function VoiceInputButton({ value, onChangeText, testID, disabled }: VoiceInputButtonProps) {
  const { colors, radii } = useTheme();
  const [listening, setListening] = useState(false);
  const [unavailableHint, setUnavailableHint] = useState<string | null>(null);
  // Text present when dictation started; interim results replace each other,
  // so every event rebuilds from this base rather than appending repeatedly.
  const baseTextRef = useRef("");
  // Finalized segments from the current session: interim results only cover
  // the latest utterance, so finished utterances accumulate here.
  const finalizedRef = useRef("");
  const pulse = useRef(new Animated.Value(1)).current;

  useSpeechRecognitionEvent("start", () => {
    setListening(true);
    setUnavailableHint(null);
  });
  useSpeechRecognitionEvent("end", () => setListening(false));
  useSpeechRecognitionEvent("result", (event) => {
    const transcript = event.results[0]?.transcript ?? "";
    if (!transcript) return;
    if (event.isFinal) {
      finalizedRef.current = joinDictation(finalizedRef.current, transcript);
    }
    const session = event.isFinal
      ? finalizedRef.current
      : joinDictation(finalizedRef.current, transcript);
    onChangeText(joinDictation(baseTextRef.current, session));
  });
  useSpeechRecognitionEvent("error", (event) => {
    setListening(false);
    if (event.error === "not-allowed" || event.error === "service-not-allowed") {
      setUnavailableHint(
        "Voice input isn't allowed — you can still dictate with the keyboard microphone."
      );
    } else {
      setUnavailableHint("Voice input is unavailable right now — you can keep typing.");
    }
  });

  // Pulse the mic while listening.
  useEffect(() => {
    if (!listening) {
      pulse.setValue(1);
      return;
    }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 0.35, duration: 600, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 1, duration: 600, useNativeDriver: true }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [listening, pulse]);

  // Never leave the recognizer running if the screen unmounts mid-dictation.
  useEffect(
    () => () => {
      if (Platform.OS === "ios") ExpoSpeechRecognitionModule.abort();
    },
    []
  );

  if (Platform.OS !== "ios") return null;

  const toggle = async () => {
    if (listening) {
      ExpoSpeechRecognitionModule.stop();
      return;
    }
    const permissions = await ExpoSpeechRecognitionModule.requestPermissionsAsync();
    if (!permissions.granted) {
      setUnavailableHint(
        "Microphone access is off — you can still dictate with the keyboard microphone."
      );
      return;
    }
    baseTextRef.current = value;
    finalizedRef.current = "";
    ExpoSpeechRecognitionModule.start({
      lang: "en-GB",
      interimResults: true,
      // Auto-stops on a few seconds of silence (iOS); tap again to stop sooner.
      continuous: false,
      requiresOnDeviceRecognition: true,
      addsPunctuation: true,
      contextualStrings: VOICE_CONTEXTUAL_STRINGS,
      iosTaskHint: "dictation",
    });
  };

  return (
    <View style={styles.container}>
      <Pressable
        testID={testID}
        accessibilityLabel={listening ? "Stop dictation" : "Start dictation"}
        accessibilityRole="button"
        onPress={toggle}
        disabled={disabled}
        hitSlop={8}
        style={[
          styles.button,
          {
            borderRadius: radii.full,
            backgroundColor: listening ? colors.error : colors.surface,
            opacity: disabled ? 0.5 : 1,
          },
        ]}
      >
        <Animated.View style={{ opacity: listening ? pulse : 1 }}>
          <Icon name="mic" size={18} color={listening ? "#FFFFFF" : colors.textSecondary} />
        </Animated.View>
      </Pressable>
      {listening && (
        <Text variant="caption" style={{ color: colors.error }}>
          Listening…
        </Text>
      )}
      {!listening && unavailableHint && (
        <Text variant="caption" color="secondary" style={styles.hint}>
          {unavailableHint}
        </Text>
      )}
    </View>
  );
}

/** Append dictated text to whatever was typed, normalising the join space. */
function joinDictation(base: string, transcript: string): string {
  const trimmedBase = base.replace(/\s+$/, "");
  if (!trimmedBase) return transcript;
  return `${trimmedBase} ${transcript}`;
}

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  button: {
    width: 32,
    height: 32,
    alignItems: "center",
    justifyContent: "center",
  },
  hint: {
    flex: 1,
  },
});
