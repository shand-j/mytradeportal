import { Component, ErrorInfo, ReactNode } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { flushAnalytics, trackError } from "../lib/analytics";

type Props = { children: ReactNode };
type State = { failed: boolean };

export class AnalyticsErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, _info: ErrorInfo): void {
    trackError("react_render_error", {
      error_type: error.name || "Error",
      component: "root",
    });
    void flushAnalytics();
  }

  render() {
    if (this.state.failed) {
      return (
        <View style={styles.container}>
          <Text style={styles.title}>Something went wrong</Text>
          <Text style={styles.body}>The error has been reported. You can try this screen again.</Text>
          <Pressable style={styles.button} onPress={() => this.setState({ failed: false })}>
            <Text style={styles.buttonText}>Try again</Text>
          </Pressable>
        </View>
      );
    }
    return this.props.children;
  }
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
    backgroundColor: "#ffffff",
  },
  title: { fontSize: 22, fontWeight: "600", color: "#18181b", marginBottom: 12 },
  body: { fontSize: 16, color: "#52525b", textAlign: "center", marginBottom: 24 },
  button: { backgroundColor: "#18181b", borderRadius: 8, paddingHorizontal: 20, paddingVertical: 12 },
  buttonText: { color: "#ffffff", fontSize: 16, fontWeight: "600" },
});
