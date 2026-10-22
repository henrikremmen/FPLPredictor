import { QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { SessionProvider } from "../src/context/session-context";
import { WorkspaceProvider } from "../src/context/workspace-context";
import { queryClient } from "../src/lib/query-client";
import { colors } from "../src/theme";

export default function RootLayout() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <QueryClientProvider client={queryClient}>
          <SessionProvider>
            <WorkspaceProvider>
            <StatusBar style="light" />
            <Stack
              screenOptions={{
                headerShown: false,
                contentStyle: { backgroundColor: colors.background },
              }}
            >
              <Stack.Screen name="(tabs)" />
              <Stack.Screen name="onboarding" options={{ presentation: "fullScreenModal" }} />
              <Stack.Screen
                name="lineup"
                options={{
                  headerShown: true, title: "Lineup", headerBackTitle: "Round",
                  headerStyle: { backgroundColor: colors.background }, headerTintColor: colors.textPrimary,
                }}
              />
              <Stack.Screen
                name="timeline"
                options={{
                  headerShown: true, title: "Timeline", headerBackTitle: "History",
                  headerStyle: { backgroundColor: colors.background }, headerTintColor: colors.textPrimary,
                }}
              />
              <Stack.Screen
                name="correction"
                options={{ presentation: "modal", headerShown: true, title: "Edit squad" }}
              />
            </Stack>
            </WorkspaceProvider>
          </SessionProvider>
        </QueryClientProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
