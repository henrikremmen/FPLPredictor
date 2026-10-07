import { Redirect, Tabs } from "expo-router";
import { Text } from "react-native";
import { useSession } from "../../src/context/session-context";
import { colors } from "../../src/theme";

function TabIcon({ symbol, focused }: { symbol: string; focused: boolean }) {
  return <Text style={{ fontSize: 20, opacity: focused ? 1 : 0.55 }}>{symbol}</Text>;
}

export default function TabsLayout() {
  const { isLoading, isOnboarded } = useSession();

  if (isLoading) return null;
  if (!isOnboarded) return <Redirect href="/onboarding" />;

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.border },
        tabBarActiveTintColor: colors.accent,
        tabBarInactiveTintColor: colors.textMuted,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{ title: "Overview", tabBarIcon: ({ focused }) => <TabIcon symbol="🏠" focused={focused} /> }}
      />
      <Tabs.Screen
        name="pitch"
        options={{ title: "Squad", tabBarIcon: ({ focused }) => <TabIcon symbol="⚽" focused={focused} /> }}
      />
      <Tabs.Screen
        name="transfers"
        options={{ title: "Transfers", tabBarIcon: ({ focused }) => <TabIcon symbol="🔁" focused={focused} /> }}
      />
      <Tabs.Screen
        name="strategy"
        options={{ title: "Strategy", tabBarIcon: ({ focused }) => <TabIcon symbol="🧭" focused={focused} /> }}
      />
      <Tabs.Screen
        name="market"
        options={{ title: "Market", tabBarIcon: ({ focused }) => <TabIcon symbol="🛒" focused={focused} /> }}
      />
      <Tabs.Screen
        name="analytics"
        options={{ title: "Analytics", tabBarIcon: ({ focused }) => <TabIcon symbol="📊" focused={focused} /> }}
      />
    </Tabs>
  );
}
