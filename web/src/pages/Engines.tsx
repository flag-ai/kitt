import { useQuery } from "@tanstack/react-query";
import { listEngines } from "../api/engines";

export function Engines() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["engines"],
    queryFn: listEngines,
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-mauve">Engines</h1>
      {isLoading && <p className="text-subtext-1">Loading engines…</p>}
      {error && (
        <p className="text-red">
          Failed to load engines. Is the admin token set?
        </p>
      )}
      {data && (
        <table className="w-full text-sm">
          <thead className="bg-mantle">
            <tr className="text-left text-subtext-0">
              <th className="p-3">Name</th>
              <th className="p-3">Display</th>
              <th className="p-3">Image</th>
              <th className="p-3">Formats</th>
              <th className="p-3">Modes</th>
              <th className="p-3">Default port</th>
            </tr>
          </thead>
          <tbody>
            {data.map((e) => (
              <tr key={e.name} className="border-b border-surface-1">
                <td className="p-3 text-blue">{e.name}</td>
                <td className="p-3">{e.display_name}</td>
                <td className="p-3 text-subtext-0">{e.docker_image || "—"}</td>
                <td className="p-3 text-subtext-0">{e.formats.join(", ")}</td>
                <td className="p-3 text-subtext-0">{e.modes.join(", ")}</td>
                <td className="p-3 text-subtext-0">{e.default_port}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
