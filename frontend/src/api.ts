import type {
  ChipStrategy,
  Position,
  RiskProfile,
  TeamResponse,
  TransferResponse,
  Player,
} from "./types";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail ?? `HTTP ${response.status}`);
  }
  return payload as T;
}

export const api = {
  importTeam(reference: string, horizon: number, riskProfile: RiskProfile) {
    return request<TeamResponse>("/api/team/import", {
      method: "POST",
      body: JSON.stringify({ reference, horizon, risk_profile: riskProfile }),
    });
  },
  updateSettings(session: string, bank: number, freeTransfers: number) {
    return request<TeamResponse>(`/api/team/${session}/settings`, {
      method: "PATCH",
      body: JSON.stringify({ bank, free_transfers: freeTransfers }),
    });
  },
  transfers(session: string, number: number) {
    return request<TransferResponse>(`/api/team/${session}/transfers`, {
      method: "POST",
      body: JSON.stringify({ number }),
    });
  },
  chips(session: string) {
    return request<ChipStrategy>(`/api/team/${session}/chips`, { method: "POST" });
  },
  async market(session: string, position: Position | "ALL", maxPrice: number) {
    const params = new URLSearchParams({ limit: "30", max_price: String(maxPrice) });
    if (position !== "ALL") params.set("position", position);
    return request<{ players: Player[] }>(`/api/team/${session}/market?${params}`);
  },
  async sells(session: string) {
    return request<{ players: Player[] }>(`/api/team/${session}/sells`);
  },
  refreshForecast() {
    return request<{ status: string }>("/api/forecast/refresh", { method: "POST" });
  },
};
