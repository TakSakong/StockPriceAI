import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ScanResults } from "../scanner/ScanResults";
import type { ScanResultOut } from "@/types/api";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

function makeResult(overrides: Partial<ScanResultOut> = {}): ScanResultOut {
  return {
    id: "r1",
    job_id: "j1",
    ticker: "AAPL",
    composite_score: 0.75,
    up_prob: 0.65,
    signal: "BUY",
    sector: "Technology",
    est_upside: 12.5,
    cached_at: "2026-01-01",
    ...overrides,
  };
}

describe("ScanResults", () => {
  it("renders result count in header", () => {
    const results = [makeResult({ ticker: "AAPL" }), makeResult({ id: "r2", ticker: "MSFT" })];
    render(<ScanResults results={results} />);
    expect(screen.getByText("스캔 결과 (2종목)")).toBeTruthy();
  });

  it("renders ticker symbols as links", () => {
    render(<ScanResults results={[makeResult({ ticker: "TSLA" })]} />);
    const link = screen.getByRole("link", { name: "TSLA" });
    expect(link).toBeTruthy();
    expect((link as HTMLAnchorElement).href).toContain("ticker=TSLA");
  });

  it("sorts results by composite_score descending", () => {
    const results = [
      makeResult({ id: "r1", ticker: "LOW", composite_score: 0.3 }),
      makeResult({ id: "r2", ticker: "HIGH", composite_score: 0.9 }),
      makeResult({ id: "r3", ticker: "MID", composite_score: 0.6 }),
    ];
    render(<ScanResults results={results} />);
    const rows = screen.getAllByRole("row");
    // rows[0] is thead, rows[1..] are tbody
    expect(rows[1].textContent).toContain("HIGH");
    expect(rows[2].textContent).toContain("MID");
    expect(rows[3].textContent).toContain("LOW");
  });

  it("renders '—' for missing optional fields", () => {
    const result = makeResult({
      signal: undefined,
      up_prob: undefined,
      est_upside: undefined,
      composite_score: undefined,
      sector: undefined,
    });
    render(<ScanResults results={[result]} />);
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(4);
  });

  it("renders up_prob as percentage", () => {
    render(<ScanResults results={[makeResult({ up_prob: 0.723 })]} />);
    expect(screen.getByText("72.3%")).toBeTruthy();
  });

  it("renders positive est_upside with '+' prefix", () => {
    render(<ScanResults results={[makeResult({ est_upside: 15.5 })]} />);
    expect(screen.getByText("+15.5%")).toBeTruthy();
  });

  it("renders negative est_upside without '+' prefix", () => {
    render(<ScanResults results={[makeResult({ est_upside: -8.3 })]} />);
    expect(screen.getByText("-8.3%")).toBeTruthy();
  });

  it("renders BUY signal badge", () => {
    render(<ScanResults results={[makeResult({ signal: "BUY" })]} />);
    expect(screen.getByText("BUY")).toBeTruthy();
  });

  it("renders composite_score with 3 decimal places", () => {
    render(<ScanResults results={[makeResult({ composite_score: 0.123456 })]} />);
    expect(screen.getByText("0.123")).toBeTruthy();
  });

  it("renders table with 0 results (empty body)", () => {
    render(<ScanResults results={[]} />);
    expect(screen.getByText("스캔 결과 (0종목)")).toBeTruthy();
  });
});
