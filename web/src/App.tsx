import { NavLink, Route, Routes } from "react-router-dom";
import { Dashboard } from "./pages/Dashboard";
import { Engines } from "./pages/Engines";
import { Recommend } from "./pages/Recommend";
import { Placeholder } from "./pages/Placeholder";

const navItems = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/bonnie-agents", label: "BONNIE Agents" },
  { to: "/models", label: "Models" },
  { to: "/campaigns", label: "Campaigns" },
  { to: "/quicktest", label: "Quick Test" },
  { to: "/results", label: "Results" },
  { to: "/engines", label: "Engines" },
  { to: "/benchmarks", label: "Benchmarks" },
  { to: "/recommend", label: "Recommend" },
  { to: "/notifications", label: "Notifications" },
  { to: "/settings", label: "Settings" },
];

export function App() {
  return (
    <div className="min-h-screen flex bg-base">
      <aside className="w-56 bg-mantle border-r border-surface-1 p-4 space-y-1">
        <div className="text-mauve text-lg font-bold mb-4 px-2">KITT 2.0</div>
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              `block rounded-md px-3 py-2 text-sm transition-colors ${
                isActive
                  ? "bg-surface-1 text-text"
                  : "text-subtext-0 hover:text-text hover:bg-surface-0"
              }`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </aside>
      <main className="flex-1 p-8 overflow-auto">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/engines" element={<Engines />} />
          <Route path="/recommend" element={<Recommend />} />
          <Route
            path="/bonnie-agents"
            element={<Placeholder title="BONNIE Agents" />}
          />
          <Route path="/models" element={<Placeholder title="Models" />} />
          <Route
            path="/campaigns"
            element={<Placeholder title="Campaigns" />}
          />
          <Route
            path="/quicktest"
            element={<Placeholder title="Quick Test" />}
          />
          <Route path="/results" element={<Placeholder title="Results" />} />
          <Route
            path="/benchmarks"
            element={<Placeholder title="Benchmarks" />}
          />
          <Route
            path="/notifications"
            element={<Placeholder title="Notifications" />}
          />
          <Route path="/settings" element={<Placeholder title="Settings" />} />
        </Routes>
      </main>
    </div>
  );
}
