import { render, screen } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { queryClient } from "../lib/query-client";
import { LoginPage } from "./login-page";

describe("LoginPage", () => {
  it("renders the admin operator heading", () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <LoginPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByText(/Admin operator sign-in/i)).toBeInTheDocument();
  });
});
