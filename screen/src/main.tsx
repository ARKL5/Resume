import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import ScreenBoard from "./screen-board"
import "./index.css"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ScreenBoard />
  </StrictMode>,
)
