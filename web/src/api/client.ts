import { useEffect, useState } from "react";
import { mockFor } from "./fixtures";

/*
 * The app is served under /audits/ behind the shared tunnel, so the API lives at
 * /audits/api — not /api. Deriving it from BASE_URL keeps the two in step at every
 * base the bundle is ever built with; the sibling app hardcoded "/api" and broke
 * the moment it moved off the root.
 */
export const API_BASE = `${import.meta.env.BASE_URL.replace(/\/$/, "")}/api`;

/** Raised when a response comes from fixtures, so the shell can say so. */
export const MOCK_EVENT = "audits:mock";

let mocking = false;
export const isMocking = () => mocking;

function fellBack(reason: string) {
  if (!mocking) {
    mocking = true;
    console.warn(`[audits] API unreachable (${reason}); serving fixtures.`);
  }
  window.dispatchEvent(new Event(MOCK_EVENT));
}

/**
 * Fetch a contract path, falling back to fixtures when the API is not there.
 *
 * A fixture is never silent: `mock` comes back true and the shell raises a
 * banner. If the API answers but with something unparseable that is a real
 * error and it surfaces as one — bending the UI to a shape the contract does
 * not describe would hide a genuine disagreement between the two agents.
 */
export async function get<T>(path: string, signal?: AbortSignal): Promise<{ data: T; mock: boolean }> {
  try {
    const res = await fetch(`${API_BASE}${path}`, { signal, headers: { accept: "application/json" } });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return { data: (await res.json()) as T, mock: false };
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    fellBack(e instanceof Error ? e.message : String(e));
    return { data: mockFor(path) as T, mock: true };
  }
}

export interface Resource<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  mock: boolean;
}

/** One GET, re-run whenever `path` changes. Null path means "nothing to fetch". */
export function useResource<T>(path: string | null): Resource<T> {
  const [state, setState] = useState<Resource<T>>({ data: null, error: null, loading: path !== null, mock: false });

  useEffect(() => {
    if (path === null) {
      setState({ data: null, error: null, loading: false, mock: false });
      return;
    }
    const ac = new AbortController();
    setState((s) => ({ ...s, loading: true, error: null }));
    get<T>(path, ac.signal)
      .then(({ data, mock }) => setState({ data, error: null, loading: false, mock }))
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setState({ data: null, error: e instanceof Error ? e : new Error(String(e)), loading: false, mock: false });
      });
    return () => ac.abort();
  }, [path]);

  return state;
}
