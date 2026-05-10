"use client";

import { create } from "zustand";

interface UIState {
  selectedTicker: string;
  activeTab: string;
  setSelectedTicker: (ticker: string) => void;
  setActiveTab: (tab: string) => void;
}

export const useUIStore = create<UIState>()((set) => ({
  selectedTicker: "",
  activeTab: "overview",
  setSelectedTicker: (ticker) => set({ selectedTicker: ticker, activeTab: "overview" }),
  setActiveTab: (tab) => set({ activeTab: tab }),
}));
