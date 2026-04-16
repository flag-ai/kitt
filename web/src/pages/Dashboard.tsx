import { useQuery } from "@tanstack/react-query";
import { listEngines } from "../api/engines";

export function Dashboard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["engines"],
    queryFn: listEngines,
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-mauve">Dashboard</h1>
      <p className="text-subtext-0">
        KITT 2.0 is a benchmarking suite for LLM inference engines. This
        early dashboard surfaces the registered engines as a smoke test;
        richer widgets (recent runs, campaign status, active agents) arrive
        as the server-side services come online.
      </p>
      <section>
        <h2 className="text-lg text-lavender mb-3">Registered engines</h2>
        {isLoading && <p className="text-subtext-1">Loading engines…</p>}
        {error && (
          <p className="text-red">
            Failed to load engines. Set the admin token via the Settings page
            if you see a 401.
          </p>
        )}
        {data && (
          <ul className="grid grid-cols-2 gap-3">
            {data.map((e) => (
              <li
                key={e.name}
                className="bg-surface-0 rounded-md p-4 border border-surface-1"
              >
                <div className="text-text font-semibold">{e.display_name}</div>
                <div className="text-subtext-0 text-sm">{e.description}</div>
                <div className="mt-2 text-xs text-overlay-2">
                  Port {e.default_port} · {e.modes.join(" / ")}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
