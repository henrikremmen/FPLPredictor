import { ApiClient, ApiError } from "@fplmodell/api-client";

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

describe("ApiClient", () => {
  it("sends player preferences to optimisers and posts comparisons", async () => {
    const fetchImpl = jest.fn().mockResolvedValue(jsonResponse(200, {}));
    const client = new ApiClient({ baseUrl: "http://example.test", fetchImpl });
    const constraints = { locked_ids: [8], excluded_ids: [16] };
    await client.transfers("s", 1, [], constraints);
    await client.compare("s", 8, 16, constraints);
    const bodies = fetchImpl.mock.calls.map(([, init]) => JSON.parse(init.body));
    expect(bodies[0]).toEqual({ number: 1, outgoing_ids: [], locked_ids: [8], excluded_ids: [16] });
    expect(fetchImpl.mock.calls[1][0]).toBe("http://example.test/api/team/s/compare");
    expect(bodies[1]).toEqual({ out_id: 8, in_id: 16, locked_ids: [8], excluded_ids: [16] });
  });

  it("calls the global fetch unbound, as browsers require (Expo web)", async () => {
    const original = global.fetch;
    global.fetch = jest.fn(function (this: unknown) {
      if (this !== undefined && this !== globalThis) throw new TypeError("Illegal invocation");
      return Promise.resolve(jsonResponse(200, { status: "ok", uptime_seconds: 1, active_sessions: 0 }));
    }) as unknown as typeof fetch;
    try {
      await expect(new ApiClient({ baseUrl: "http://example.test" }).health()).resolves.toMatchObject({ status: "ok" });
    } finally {
      global.fetch = original;
    }
  });

  it("resolves with the parsed payload on success", async () => {
    const fetchImpl = jest.fn().mockResolvedValue(jsonResponse(200, { status: "ok", uptime_seconds: 1, active_sessions: 0 }));
    const client = new ApiClient({ baseUrl: "http://example.test", fetchImpl });

    await expect(client.health()).resolves.toEqual({ status: "ok", uptime_seconds: 1, active_sessions: 0 });
    expect(fetchImpl).toHaveBeenCalledWith("http://example.test/api/health", expect.any(Object));
  });

  it("maps a non-ok response to an ApiError with kind 'http' and the backend's detail", async () => {
    const fetchImpl = jest.fn().mockResolvedValue(jsonResponse(404, { detail: "The team session does not exist." }));
    const client = new ApiClient({ baseUrl: "http://example.test", fetchImpl });

    await expect(client.getTeam("missing")).rejects.toMatchObject({
      kind: "http",
      status: 404,
      message: "The team session does not exist.",
    });
  });

  it("maps a rejected fetch (device offline / backend unreachable) to kind 'network'", async () => {
    const fetchImpl = jest.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    const client = new ApiClient({ baseUrl: "http://example.test", fetchImpl });

    await expect(client.health()).rejects.toBeInstanceOf(ApiError);
    await expect(client.health()).rejects.toMatchObject({ kind: "network" });
  });

  it("maps an aborted request to kind 'timeout' once the per-call timeout elapses", async () => {
    const fetchImpl = jest.fn().mockImplementation(
      (_url: string, options: RequestInit) =>
        new Promise((_resolve, reject) => {
          options.signal?.addEventListener("abort", () => {
            const error = new Error("Aborted");
            error.name = "AbortError";
            reject(error);
          });
        }),
    );
    const client = new ApiClient({ baseUrl: "http://example.test", timeoutMs: 20, fetchImpl });

    await expect(client.health()).rejects.toMatchObject({ kind: "timeout" });
  });
});
