"use client";

import { createContext, useContext, type ReactNode } from "react";

export type PrepCatalogTopic = {
  id: number;
  slug: string;
  name: string;
  description: string;
  difficulty: string;
};

export type PrepLanguageKey = "python" | "javascript" | "typescript" | "java" | "cpp";

export type PrepCatalogTestCase = {
  id: number;
  title: string;
  input: Record<string, unknown>;
  expected_output: string;
  explanation: string;
  is_hidden: boolean;
  position: number;
};

export type PrepCatalogProblem = {
  id: number;
  slug: string;
  title: string;
  prompt: string;
  difficulty: string;
  estimated_minutes: number;
  topic_name: string;
  topic_slug: string;
  expected_concepts: string[];
  constraints: string[];
  hint: string;
  starter_code: Partial<Record<PrepLanguageKey, string>>;
  available_languages: PrepLanguageKey[];
  test_cases: PrepCatalogTestCase[];
};

type PrepCatalogValue = {
  topics: PrepCatalogTopic[];
  problems: PrepCatalogProblem[];
  refreshCatalog: () => Promise<void>;
};

const PrepCatalogContext = createContext<PrepCatalogValue | null>(null);

export function PrepCatalogProvider({
  value,
  children,
}: Readonly<{ value: PrepCatalogValue; children: ReactNode }>) {
  return <PrepCatalogContext.Provider value={value}>{children}</PrepCatalogContext.Provider>;
}

export function usePrepCatalog(): PrepCatalogValue {
  const catalog = useContext(PrepCatalogContext);
  if (!catalog) throw new Error("usePrepCatalog must be used within PrepCatalogProvider");
  return catalog;
}
