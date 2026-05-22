import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StockSearch } from "../stock/StockSearch";

describe("StockSearch", () => {
  it("renders input and 분석 button", () => {
    render(<StockSearch onSearch={vi.fn()} />);
    expect(screen.getByPlaceholderText("티커 입력 (예: AAPL)")).toBeTruthy();
    expect(screen.getByRole("button", { name: "분석" })).toBeTruthy();
  });

  it("submit button is disabled when input is empty", () => {
    render(<StockSearch onSearch={vi.fn()} />);
    const btn = screen.getByRole("button", { name: "분석" });
    expect((btn as HTMLButtonElement).disabled).toBe(true);
  });

  it("submit button is enabled after typing", async () => {
    render(<StockSearch onSearch={vi.fn()} />);
    const input = screen.getByPlaceholderText("티커 입력 (예: AAPL)");
    await userEvent.type(input, "aapl");
    const btn = screen.getByRole("button", { name: "분석" });
    expect((btn as HTMLButtonElement).disabled).toBe(false);
  });

  it("calls onSearch with uppercase ticker on form submit", async () => {
    const onSearch = vi.fn();
    render(<StockSearch onSearch={onSearch} />);
    const input = screen.getByPlaceholderText("티커 입력 (예: AAPL)");
    await userEvent.type(input, "aapl");
    await userEvent.click(screen.getByRole("button", { name: "분석" }));
    expect(onSearch).toHaveBeenCalledOnce();
    expect(onSearch).toHaveBeenCalledWith("AAPL");
  });

  it("clears input after submit", async () => {
    render(<StockSearch onSearch={vi.fn()} />);
    const input = screen.getByPlaceholderText("티커 입력 (예: AAPL)") as HTMLInputElement;
    await userEvent.type(input, "tsla");
    await userEvent.click(screen.getByRole("button", { name: "분석" }));
    expect(input.value).toBe("");
  });

  it("does not call onSearch when input is whitespace only", async () => {
    const onSearch = vi.fn();
    render(<StockSearch onSearch={onSearch} />);
    const input = screen.getByPlaceholderText("티커 입력 (예: AAPL)");
    await userEvent.type(input, "   ");
    await userEvent.keyboard("{Enter}");
    expect(onSearch).not.toHaveBeenCalled();
  });

  it("renders popular tickers (AAPL, TSLA, NVDA ...)", () => {
    render(<StockSearch onSearch={vi.fn()} />);
    expect(screen.getByText("AAPL")).toBeTruthy();
    expect(screen.getByText("TSLA")).toBeTruthy();
    expect(screen.getByText("NVDA")).toBeTruthy();
  });

  it("calls onSearch directly when popular ticker button is clicked", async () => {
    const onSearch = vi.fn();
    render(<StockSearch onSearch={onSearch} />);
    await userEvent.click(screen.getByText("MSFT"));
    expect(onSearch).toHaveBeenCalledOnce();
    expect(onSearch).toHaveBeenCalledWith("MSFT");
  });
});
