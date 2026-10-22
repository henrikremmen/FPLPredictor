import { Redirect, Tabs } from "expo-router";
import { useSession } from "../../src/context/session-context";
import { Icons } from "../../src/components/icons";
import { colors } from "../../src/theme";

/** Five sections, the same as the web app: This round, Transfers & plan, Players, History, My team. */
const TABS = [
  { name: "index", title: "Round", label: "This round", Icon: Icons.Home },
  { name: "plan", title: "Plan", label: "Transfers and plan", Icon: Icons.Swap },
  { name: "players", title: "Players", label: "Players", Icon: Icons.Users },
  { name: "history", title: "History", label: "History", Icon: Icons.Calendar },
  { name: "team", title: "Team", label: "My team", Icon: Icons.Shield },
] as const;

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
      {TABS.map(({ name, title, label, Icon }) => (
        <Tabs.Screen key={name} name={name} options={{
          title, tabBarAccessibilityLabel: label,
          tabBarIcon: ({ color }) => <Icon color={String(color)} />,
        }} />
      ))}
    </Tabs>
  );
}
