import { useEffect, useState } from "react";

/*
 * Hash routing.
 *
 * Same choice as the renewal dashboard: three screens do not justify a router
 * dependency, and a hash route survives a refresh whatever the server does with
 * unknown paths.
 */
export type Route =
  | { name: "overview" }
  /* variable/variableVerdict come from clicking a row on the Overview's
     variable table: "show me the calls behind this number". They live in the
     hash rather than in CallList state so the link is shareable and survives a
     refresh, which is the whole point of clicking through to evidence. */
  | { name: "calls"; variable?: string; variableVerdict?: "missed" | "wrong" }
  | { name: "call"; id: number }
  | { name: "manual" }
  | { name: "runs" };

export function currentRoute(): Route {
  const [path, search] = window.location.hash.replace(/^#\/?/, "").split("?");
  const hash = path ?? "";
  const call = /^calls\/(\d+)$/.exec(hash);
  if (call) return { name: "call", id: Number(call[1]) };
  if (hash === "calls") {
    const p = new URLSearchParams(search ?? "");
    const vv = p.get("vv");
    return {
      name: "calls",
      variable: p.get("variable") || undefined,
      variableVerdict: vv === "missed" || vv === "wrong" ? vv : undefined,
    };
  }
  if (hash === "manual") return { name: "manual" };
  if (hash === "runs") return { name: "runs" };
  return { name: "overview" };
}

export function href(route: Route): string {
  if (route.name === "call") return `#/calls/${route.id}`;
  if (route.name === "calls" && route.variable) {
    const p = new URLSearchParams({ variable: route.variable });
    if (route.variableVerdict) p.set("vv", route.variableVerdict);
    return `#/calls?${p}`;
  }
  return `#/${route.name}`;
}

export function navigate(route: Route): void {
  window.location.hash = href(route);
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(currentRoute);
  useEffect(() => {
    const onChange = () => setRoute(currentRoute());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
