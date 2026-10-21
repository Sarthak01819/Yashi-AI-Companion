import { Suspense, lazy, useEffect, useState } from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import "./index.css";

const Dashboard = lazy(() => import("./dashboard/Dashboard"));

// "#/" -> chat, "#/dashboard/<tab>" -> dashboard.
function parseRoute() {
  const match = window.location.hash.match(/^#\/dashboard(?:\/(\w+))?/);
  return match ? { view: "dashboard", tab: match[1] || "profile" } : { view: "chat" };
}

function Root() {
  const [route, setRoute] = useState(parseRoute);

  useEffect(() => {
    const onHash = () => setRoute(parseRoute());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  return (
    <>
      {/* The chat stays mounted so the conversation and voice survive a dashboard visit. */}
      <div className="h-full" hidden={route.view !== "chat"}>
        <App active={route.view === "chat"} />
      </div>
      {route.view === "dashboard" ? (
        <Suspense fallback={<div className="h-full bg-[#0c0708]" />}>
          <Dashboard tab={route.tab} />
        </Suspense>
      ) : null}
    </>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<Root />);
