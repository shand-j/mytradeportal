import { Stack } from "expo-router";
import { View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";
import { QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "../src/contexts/AuthContext";
import { ThemeProvider } from "../src/theme/ThemeProvider";
import { queryClient } from "../src/lib/queryClient";
import { AnalyticsLifecycle } from "../src/components/AnalyticsLifecycle";
import { AnalyticsErrorBoundary } from "../src/components/AnalyticsErrorBoundary";
import "../global.css";

export default function RootLayout() {
  return (
    <QueryClientProvider client={queryClient}>
      <SafeAreaProvider>
        <ThemeProvider>
          <AuthProvider>
            <AnalyticsErrorBoundary>
              <AnalyticsLifecycle />
              <View style={{ flex: 1 }}>
                <Stack screenOptions={{ headerShown: false }}>
                  <Stack.Screen name="index" />
                </Stack>
              </View>
              <StatusBar style="auto" />
            </AnalyticsErrorBoundary>
          </AuthProvider>
        </ThemeProvider>
      </SafeAreaProvider>
    </QueryClientProvider>
  );
}
