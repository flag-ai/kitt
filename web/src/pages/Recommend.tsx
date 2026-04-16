import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { recommend } from "../api/engines";

export function Recommend() {
  const [vram, setVram] = useState(24);
  const [task, setTask] = useState("quality");
  const [unified, setUnified] = useState(false);

  const { data, isFetching } = useQuery({
    queryKey: ["recommend", vram, task, unified],
    queryFn: () =>
      recommend({ gpu_vram_gib: vram, task, unified_memory: unified }),
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-mauve">Recommend</h1>
      <p className="text-subtext-0">
        Describe the target hardware and task; KITT returns a ranked list of
        engine + quantization suggestions with rationale.
      </p>
      <section className="grid grid-cols-3 gap-4">
        <label className="flex flex-col gap-1">
          <span className="text-sm text-subtext-0">GPU VRAM (GiB)</span>
          <input
            type="number"
            value={vram}
            onChange={(e) => setVram(Number(e.target.value))}
            className="bg-surface-0 border border-surface-2 rounded-md px-3 py-2 text-text"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-sm text-subtext-0">Task</span>
          <select
            value={task}
            onChange={(e) => setTask(e.target.value)}
            className="bg-surface-0 border border-surface-2 rounded-md px-3 py-2 text-text"
          >
            <option value="quality">quality</option>
            <option value="performance">performance</option>
            <option value="coding">coding</option>
            <option value="multimodal">multimodal</option>
          </select>
        </label>
        <label className="flex items-center gap-2 mt-6">
          <input
            type="checkbox"
            checked={unified}
            onChange={(e) => setUnified(e.target.checked)}
          />
          <span className="text-sm text-subtext-0">
            Unified memory (Apple Silicon / DGX Spark)
          </span>
        </label>
      </section>
      <section>
        <h2 className="text-lg text-lavender mb-3">Suggestions</h2>
        {isFetching && <p className="text-subtext-1">Thinking…</p>}
        {data && data.length === 0 && (
          <p className="text-subtext-1">
            No suggestions for this combination — try a different task or
            VRAM tier.
          </p>
        )}
        {data && (
          <ol className="space-y-3">
            {data.map((s, i) => (
              <li
                key={s.engine}
                className="bg-surface-0 rounded-md p-4 border border-surface-1"
              >
                <div className="flex items-baseline justify-between">
                  <span className="text-blue font-semibold">
                    #{i + 1} · {s.engine}
                  </span>
                  <span className="text-subtext-0 text-sm">
                    score {s.score}
                  </span>
                </div>
                {s.quantization && (
                  <div className="text-peach text-sm mt-1">
                    Quantization: {s.quantization}
                  </div>
                )}
                <div className="text-subtext-1 text-sm mt-2">
                  {s.rationale}
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
