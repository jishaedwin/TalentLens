"use client";
import * as React from "react";

interface ScreeningContextValue {
  activeScreeningId: string | null;
  setActiveScreeningId: (id: string | null) => void;
}

const ScreeningContext = React.createContext<ScreeningContextValue | null>(null);

export function ScreeningProvider({ children }: { children: React.ReactNode }) {
  const [activeScreeningId, setActiveScreeningIdState] = React.useState<string | null>(null);

  React.useEffect(() => {
    const stored = window.localStorage.getItem("tl_active_screening");
    if (stored) setActiveScreeningIdState(stored);
  }, []);

  const setActiveScreeningId = React.useCallback((id: string | null) => {
    setActiveScreeningIdState(id);
    if (id) window.localStorage.setItem("tl_active_screening", id);
    else window.localStorage.removeItem("tl_active_screening");
  }, []);

  return (
    <ScreeningContext.Provider value={{ activeScreeningId, setActiveScreeningId }}>
      {children}
    </ScreeningContext.Provider>
  );
}

export function useScreening() {
  const ctx = React.useContext(ScreeningContext);
  if (!ctx) throw new Error("useScreening must be used within ScreeningProvider");
  return ctx;
}
