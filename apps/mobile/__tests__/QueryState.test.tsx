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
    expect(screen.getByText("Laster…")).toBeTruthy();
  });

  it("shows offline copy and a retry button for a network ApiError", () => {
    const refetch = jest.fn();
    render(
      <QueryState
        query={baseQuery({ isError: true, error: new ApiError("network", "Ingen kontakt."), refetch })}
      >
        {() => <Text>content</Text>}
      </QueryState>,
    );
    expect(screen.getByText("Ingen kontakt med backend")).toBeTruthy();
    fireEvent.press(screen.getByText("Prøv igjen"));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("shows timeout copy for a timeout ApiError", () => {
    render(
      <QueryState query={baseQuery({ isError: true, error: new ApiError("timeout", "For sent.") })}>
        {() => <Text>content</Text>}
      </QueryState>,
    );
    expect(screen.getByText("Tidsavbrudd")).toBeTruthy();
  });

  it("shows the empty label when isEmpty matches the data", () => {
    render(
      <QueryState query={baseQuery({ data: { players: [] } })} isEmpty={(data: any) => data.players.length === 0} emptyLabel="Ingen spillere.">
        {() => <Text>content</Text>}
      </QueryState>,
    );
    expect(screen.getByText("Ingen spillere.")).toBeTruthy();
  });

  it("renders the children with data once loaded", () => {
    render(<QueryState query={baseQuery({ data: { players: [1] } })}>{() => <Text>content</Text>}</QueryState>);
    expect(screen.getByText("content")).toBeTruthy();
  });
});
