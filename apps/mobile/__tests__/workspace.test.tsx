import AsyncStorage from "@react-native-async-storage/async-storage";
import { act, renderHook, waitFor } from "@testing-library/react-native";
import { SessionProvider } from "../src/context/session-context";
import { WorkspaceProvider, useWorkspace } from "../src/context/workspace-context";

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <SessionProvider><WorkspaceProvider>{children}</WorkspaceProvider></SessionProvider>
);

async function mounted() {
  const hook = renderHook(() => useWorkspace(), { wrapper });
  await waitFor(() => expect(hook.result.current).toBeTruthy());
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
  return hook;
}

describe("workspace preferences and saved plans", () => {
  beforeEach(async () => {
    await AsyncStorage.clear();
    await AsyncStorage.multiSet([["fplmodell.fplId", "42"], ["fplmodell.sessionId", "s1"]]);
  });

  it("keeps a player either locked or excluded and persists per team ID", async () => {
    const { result } = await mounted();
    act(() => result.current.toggleLock(7));
    expect(result.current.constraints).toEqual({ locked_ids: [7], excluded_ids: [] });
    act(() => result.current.toggleExclude(7));
    expect(result.current.constraints).toEqual({ locked_ids: [], excluded_ids: [7] });
    await waitFor(async () => expect(JSON.parse((await AsyncStorage.getItem("fplmodell.constraints.42")) ?? "null"))
      .toEqual({ locked_ids: [], excluded_ids: [7] }));

    const again = await mounted();
    await waitFor(() => expect(again.result.current.constraints.excluded_ids).toEqual([7]));
  });

  it("saves, renames and deletes plans", async () => {
    const { result } = await mounted();
    act(() => result.current.savePlan({ kind: "transfer", name: "A", horizon: 3, summary: "Net +2.00", net_gain: 2, lines: ["Out: X"] }));
    const id = result.current.plans[0].id;
    act(() => result.current.renamePlan(id, "Plan A"));
    expect(result.current.plans.map((plan) => plan.name)).toEqual(["Plan A"]);
    act(() => result.current.deletePlan(id));
    expect(result.current.plans).toEqual([]);
  });
});
