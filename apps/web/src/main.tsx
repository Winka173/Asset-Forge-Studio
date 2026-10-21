import React from "react";
import {WorkspaceErrorBoundary} from "./workspace-error";
import { createRoot } from "react-dom/client";
import { Studio } from "./studio";
import "./style.css";
import "./refinement.css";
import "./create-flow.css";
import "./creative-system.css";
import { bootDesktop } from "./desktop";

bootDesktop().then(() => createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <WorkspaceErrorBoundary><Studio /></WorkspaceErrorBoundary>
  </React.StrictMode>,
)).catch(() => { /* Native startup screen retains the actionable failure. */ });
