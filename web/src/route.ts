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
  | { name: "calls" }
  | { name: "call"; id: number }
  | { name: "runs" };

export function currentRoute(): Route {
  const hash = window.location.hash.replace(/^#\/?/, "").split("?")[0] ?? "";
  const call = /^calls\/(\d+)$/.exec(hash);
  if (call) return { name: "call", id: Number(call[1]) };
  if (hash === "calls") return { name: "calls" };
  if (hash === "runs") return { name: "runs" };
  return { name: "overview" };
}

export function href(route: Route): string {
  return route.name === "call" ? `#/calls/${route.id}` : `#/${route.name}`;
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
