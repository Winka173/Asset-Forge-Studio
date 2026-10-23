import React from "react";
import { MotionConfig } from "motion/react";
import {WorkspaceErrorBoundary} from "./workspace-error";
import { createRoot } from "react-dom/client";
import { Studio } from "./studio";
import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/shell.css";
import "./styles/app.css";
import "./styles/studios.css";
import "./styles/panels.css";
import { bootDesktop } from "./desktop";

bootDesktop().then(() => createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MotionConfig reducedMotion="user">
    <WorkspaceErrorBoundary><Studio /></WorkspaceErrorBoundary>
  </MotionConfig>
  </React.StrictMode>,
)).catch(() => { /* Native startup screen retains the actionable failure. */ });
