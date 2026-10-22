import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { cssVariables } from "@fplmodell/shared";
import App from "./App";
import "./styles.css";

// One palette for web and mobile: CSS variables come from the shared design tokens.
for (const [name, value] of Object.entries(cssVariables())) document.documentElement.style.setProperty(name, value);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
