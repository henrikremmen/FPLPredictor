import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import type { PlayerConstraints } from "@fplmodell/api-client";
import { useSession } from "./session-context";

/** A named result kept on this device, like the web app's saved plans. */
export interface SavedPlan {
  id: string;
  name: string;
  kind: "transfer" | "comparison";
  created_at: string;
  horizon: number;
  summary: string;
  /** Net expected gain after hits; colours the summary. */
  net_gain: number;
  lines: string[];
}

interface WorkspaceValue {
  constraints: PlayerConstraints;
  toggleLock: (id: number) => void;
  toggleExclude: (id: number) => void;
  clearConstraints: () => void;
  plans: SavedPlan[];
  savePlan: (plan: Omit<SavedPlan, "id" | "created_at">) => void;
  renamePlan: (id: string, name: string) => void;
  deletePlan: (id: string) => void;
}

const EMPTY: PlayerConstraints = { locked_ids: [], excluded_ids: [] };
const keys = (entry: string) => ({ constraints: `fplmodell.constraints.${entry}`, plans: `fplmodell.plans.${entry}` });

async function read<T>(key: string, fallback: T): Promise<T> {
  try {
    return JSON.parse((await AsyncStorage.getItem(key)) ?? "null") ?? fallback;
  } catch {
    return fallback;
  }
}

const WorkspaceContext = createContext<WorkspaceValue | null>(null);

/** Player preferences and saved plans per FPL team ID; they reach every optimiser call. */
export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { fplId } = useSession();
  const [constraints, setConstraints] = useState<PlayerConstraints>(EMPTY);
  const [plans, setPlans] = useState<SavedPlan[]>([]);

  useEffect(() => {
    setConstraints(EMPTY);
    setPlans([]);
    if (!fplId) return;
    read(keys(fplId).constraints, EMPTY).then(setConstraints);
    read<SavedPlan[]>(keys(fplId).plans, []).then(setPlans);
  }, [fplId]);

  const updateConstraints = useCallback((change: (current: PlayerConstraints) => PlayerConstraints) => {
    setConstraints((current) => {
      const next = change(current);
      if (fplId) AsyncStorage.setItem(keys(fplId).constraints, JSON.stringify(next));
      return next;
    });
  }, [fplId]);
  const updatePlans = useCallback((change: (current: SavedPlan[]) => SavedPlan[]) => {
    setPlans((current) => {
      const next = change(current);
      if (fplId) AsyncStorage.setItem(keys(fplId).plans, JSON.stringify(next));
      return next;
    });
  }, [fplId]);

  const value = useMemo<WorkspaceValue>(() => ({
    constraints,
    // A player is either locked or excluded, never both.
    toggleLock: (id) => updateConstraints(({ locked_ids, excluded_ids }) => ({
      locked_ids: locked_ids.includes(id) ? locked_ids.filter((x) => x !== id) : [...locked_ids, id],
      excluded_ids: excluded_ids.filter((x) => x !== id),
    })),
    toggleExclude: (id) => updateConstraints(({ locked_ids, excluded_ids }) => ({
      locked_ids: locked_ids.filter((x) => x !== id),
      excluded_ids: excluded_ids.includes(id) ? excluded_ids.filter((x) => x !== id) : [...excluded_ids, id],
    })),
    clearConstraints: () => updateConstraints(() => EMPTY),
    plans,
    savePlan: (plan) => updatePlans((current) => [
      { ...plan, id: `${Date.now()}-${Math.round(Math.random() * 1e6)}`, created_at: new Date().toISOString() }, ...current,
    ]),
    renamePlan: (id, name) => updatePlans((current) => current.map((plan) => (plan.id === id ? { ...plan, name } : plan))),
    deletePlan: (id) => updatePlans((current) => current.filter((plan) => plan.id !== id)),
  }), [constraints, plans, updateConstraints, updatePlans]);

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace(): WorkspaceValue {
  const context = useContext(WorkspaceContext);
  if (!context) throw new Error("useWorkspace must be used within WorkspaceProvider");
  return context;
}
