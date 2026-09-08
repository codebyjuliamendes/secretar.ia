"use client";

import { useEffect, useState } from "react";
import { Button } from "./ui/primitives";

type Theme = "light" | "dark";

function apply(theme: Theme) {
  document.documentElement.dataset.theme = theme;
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("light");
  useEffect(() => {
    let stored: Theme | null = null;
    try {
      stored = window.localStorage.getItem("theme") as Theme | null;
    } catch {
      stored = null;
    }
    const initial: Theme = stored ?? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    // Sincroniza o estado com a preferência já aplicada pelo script inline do <head>.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTheme(initial);
    apply(initial);
  }, []);
  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    apply(next);
    try {
      window.localStorage.setItem("theme", next);
    } catch {
      /* armazenamento indisponível */
    }
  };
  return (
    <Button variant="ghost" size="sm" onClick={toggle} aria-label={theme === "dark" ? "Ativar tema claro" : "Ativar tema escuro"}>
      {theme === "dark" ? "☀️" : "🌙"}
    </Button>
  );
}
