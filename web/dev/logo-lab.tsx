import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { LogoLab } from "./LogoLab";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <LogoLab />
  </StrictMode>,
);
