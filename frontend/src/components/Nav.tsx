import { NavLink, useLocation, useNavigate } from "react-router-dom";

export function Nav() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  return (
    <header className="nav">
      <NavLink to="/" className="brand">
        <span className="logo-mark">🌿</span>
        Darukaa.Earth
      </NavLink>
      <nav className="nav-links">
        <NavLink to="/" className={({ isActive }) => (isActive && pathname === "/" ? "active" : "")}>
          Home
        </NavLink>
        <NavLink to="/lab">Intelligence Lab</NavLink>
        <NavLink to="/knowledge">Knowledge Base</NavLink>
        <NavLink to="/about">How it reasons</NavLink>
      </nav>
      <button className="nav-cta" onClick={() => navigate("/lab")}>
        Open the Lab
      </button>
    </header>
  );
}
