import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Navbar } from "../layout/Navbar";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

const mockLogout = vi.fn();

vi.mock("@/store/auth", () => ({
  useAuthStore: vi.fn(),
}));

import { useAuthStore } from "@/store/auth";

describe("Navbar", () => {
  beforeEach(() => {
    mockLogout.mockClear();
  });

  it("renders brand name 'StockPriceAI'", () => {
    vi.mocked(useAuthStore).mockReturnValue({
      isAuthenticated: false,
      user: null,
      logout: mockLogout,
    } as ReturnType<typeof useAuthStore>);

    render(<Navbar />);
    expect(screen.getByText("StockPriceAI")).toBeTruthy();
  });

  it("renders all nav links", () => {
    vi.mocked(useAuthStore).mockReturnValue({
      isAuthenticated: false,
      user: null,
      logout: mockLogout,
    } as ReturnType<typeof useAuthStore>);

    render(<Navbar />);
    expect(screen.getByText("대시보드")).toBeTruthy();
    expect(screen.getByText("스캐너")).toBeTruthy();
    expect(screen.getByText("관심종목")).toBeTruthy();
  });

  it("shows login button when not authenticated", () => {
    vi.mocked(useAuthStore).mockReturnValue({
      isAuthenticated: false,
      user: null,
      logout: mockLogout,
    } as ReturnType<typeof useAuthStore>);

    render(<Navbar />);
    expect(screen.getByText("로그인")).toBeTruthy();
    expect(screen.queryByText("로그아웃")).toBeNull();
  });

  it("shows user email and logout button when authenticated", () => {
    vi.mocked(useAuthStore).mockReturnValue({
      isAuthenticated: true,
      user: { id: "1", email: "user@test.com" },
      logout: mockLogout,
    } as ReturnType<typeof useAuthStore>);

    render(<Navbar />);
    expect(screen.getByText("user@test.com")).toBeTruthy();
    expect(screen.getByText("로그아웃")).toBeTruthy();
    expect(screen.queryByText("로그인")).toBeNull();
  });

  it("calls logout when logout button is clicked", async () => {
    vi.mocked(useAuthStore).mockReturnValue({
      isAuthenticated: true,
      user: { id: "1", email: "user@test.com" },
      logout: mockLogout,
    } as ReturnType<typeof useAuthStore>);

    render(<Navbar />);
    await userEvent.click(screen.getByText("로그아웃"));
    expect(mockLogout).toHaveBeenCalledOnce();
  });
});
