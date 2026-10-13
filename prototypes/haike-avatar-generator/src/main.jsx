import React from "react";
import { createRoot } from "react-dom/client";
import { StudioApp } from "./StudioApp.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <StudioApp />
  </React.StrictMode>,
);
