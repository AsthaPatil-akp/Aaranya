import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Nav } from "./components/Nav";
import { Footer } from "./components/Footer";
import { Home } from "./pages/Home";
import { Lab } from "./pages/Lab";
import { Knowledge } from "./pages/Knowledge";
import { About } from "./pages/About";

export default function App() {
  const { pathname } = useLocation();
  const labMode = pathname === "/lab";
  return (
    <div className={`app-shell${labMode ? " lab-mode" : ""}`}>
      <Nav />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/lab" element={<Lab />} />
        <Route path="/knowledge" element={<Knowledge />} />
        <Route path="/about" element={<About />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      {!labMode && <Footer />}
    </div>
  );
}
