"use client";

import { type FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface StockSearchProps {
  onSearch: (ticker: string) => void;
  loading?: boolean;
}

const POPULAR = ["AAPL", "TSLA", "NVDA", "MSFT", "GOOGL", "AMZN", "META"];

export function StockSearch({ onSearch, loading = false }: StockSearchProps) {
  const [value, setValue] = useState("");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const ticker = value.trim().toUpperCase();
    if (ticker) {
      onSearch(ticker);
      setValue("");
    }
  }

  return (
    <div className="space-y-3">
      <form onSubmit={handleSubmit} className="flex gap-2">
        <Input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="티커 입력 (예: AAPL)"
          className="flex-1 text-lg"
        />
        <Button type="submit" loading={loading} disabled={!value.trim()}>
          분석
        </Button>
      </form>
      <div className="flex flex-wrap gap-2">
        {POPULAR.map((ticker) => (
          <button
            key={ticker}
            onClick={() => onSearch(ticker)}
            className="rounded-md border border-[#4a5568] bg-[#2d3748] px-3 py-1 text-xs text-[#a0aec0] hover:border-blue-500 hover:text-blue-400 transition-colors"
          >
            {ticker}
          </button>
        ))}
      </div>
    </div>
  );
}
