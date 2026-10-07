import { Text } from "react-native";
import { render, screen, fireEvent } from "@testing-library/react-native";
import { ApiError } from "@fplmodell/api-client";
import { QueryState } from "../src/components/QueryState";

function baseQuery(overrides: Partial<Parameters<typeof QueryState>[0]["query"]>) {
  return {
    data: undefined,
    isLoading: false,
    isFetching: false,
    isError: false,
    error: null,
    refetch: jest.fn(),
    ...overrides,
  };
}

describe("QueryState", () => {
  it("shows a loading indicator while isLoading is true", () => {
    render(
      <QueryState query={baseQuery({ isLoading: true })}>{() => <Text>content</Text>}</QueryState>,
    );
    expect(screen.getByText("Loading…")).toBeTruthy();
  });

  it("shows offline copy and a retry button for a network ApiError", () => {
    const refetch = jest.fn();
    render(
      <QueryState
        query={baseQuery({ isError: true, error: new ApiError("network", "No contact."), refetch })}
      >
        {() => <Text>content</Text>}
      </QueryState>,
    );
    expect(screen.getByText("Cannot connect to backend")).toBeTruthy();
    fireEvent.press(screen.getByText("Try again"));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("shows timeout copy for a timeout ApiError", () => {
    render(
      <QueryState query={baseQuery({ isError: true, error: new ApiError("timeout", "Too late.") })}>
        {() => <Text>content</Text>}
      </QueryState>,
    );
    expect(screen.getByText("Timeout")).toBeTruthy();
  });

  it("shows the empty label when isEmpty matches the data", () => {
    render(
      <QueryState query={baseQuery({ data: { players: [] } })} isEmpty={(data: any) => data.players.length === 0} emptyLabel="No players.">
        {() => <Text>content</Text>}
      </QueryState>,
    );
    expect(screen.getByText("No players.")).toBeTruthy();
  });

  it("renders the children with data once loaded", () => {
    render(<QueryState query={baseQuery({ data: { players: [1] } })}>{() => <Text>content</Text>}</QueryState>);
    expect(screen.getByText("content")).toBeTruthy();
  });
});
