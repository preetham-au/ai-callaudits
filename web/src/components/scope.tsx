/*
 * The scope: which calls the whole screen is about.
 *
 * Held once in the shell rather than per page, and turned into query parameters
 * in exactly one place. Overview, the call list and the CSV link all build their
 * URL from this, so a filter cannot mean one thing in a heading and another in
 * the download sitting next to it. That drift is why the numbers on screen and
 * the numbers in the sheet stopped agreeing.
 */
export type Scope = {
  voicemail: "" | "only" | "exclude";
  /** Seconds. "" means no length filter at all, which is not the same as 0. */
  minDuration: string;
};

export const EMPTY_SCOPE: Scope = { voicemail: "", minDuration: "" };

/** Appends the scope to an existing URLSearchParams. Empty means "not filtered". */
export function withScope(p: URLSearchParams, s: Scope): URLSearchParams {
  if (s.voicemail) p.set("voicemail", s.voicemail);
  if (s.minDuration) p.set("min_duration", s.minDuration);
  return p;
}

/** Plain words for what is being excluded, so a filtered count never reads as the day. */
export function scopeLabel(s: Scope): string {
  const parts = [
    s.voicemail === "only" ? "voicemail only" : s.voicemail === "exclude" ? "voicemail excluded" : "",
    s.minDuration ? `longer than ${s.minDuration}s` : "",
  ].filter(Boolean);
  return parts.join(" · ");
}

const LENGTHS = ["", "20", "30", "60"];

export function ScopeFilters({ value, onChange }: { value: Scope; onChange: (s: Scope) => void }) {
  return (
    <>
      <label className="topbar-date">
        <span>Voicemail</span>
        <select
          className="select-input"
          value={value.voicemail}
          onChange={(e) => onChange({ ...value, voicemail: e.target.value as Scope["voicemail"] })}
        >
          <option value="">Include</option>
          <option value="exclude">Exclude</option>
          <option value="only">Only voicemail</option>
        </select>
      </label>
      <label className="topbar-date">
        <span>Call length</span>
        <select
          className="select-input"
          value={value.minDuration}
          onChange={(e) => onChange({ ...value, minDuration: e.target.value })}
        >
          {LENGTHS.map((v) => (
            <option key={v} value={v}>
              {v ? `Over ${v}s` : "Any length"}
            </option>
          ))}
        </select>
      </label>
    </>
  );
}
