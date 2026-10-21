import React from "react";
import { createRoot } from "react-dom/client";
import { Studio } from "./studio";
import "./style.css";
import "./refinement.css";
import { bootDesktop } from "./desktop";

bootDesktop().then(() => createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Studio />
  </React.StrictMode>,
)).catch(() => { /* Native startup screen retains the actionable failure. */ });
