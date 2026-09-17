import { Link } from "react-router-dom";

export function Footer() {
  return (
    <footer className="site-footer">
      <div>
        <div className="brand">
          <span className="logo-mark">🌿</span> Darukaa.Earth
        </div>
        <p className="tiny">
          An evidence-grounded biodiversity intelligence prototype. Recommendations are retrieved from a scientific
          knowledge base, not invented citations.
        </p>
      </div>
      <div>
        <h4>Explore</h4>
        <p><Link to="/lab">Intelligence Lab</Link></p>
        <p><Link to="/knowledge">Documents</Link></p>
        <p><Link to="/about">Architecture</Link></p>
      </div>
      <div>
        <h4>Grounding</h4>
        <p>RAG retrieval</p>
        <p>Multi-metric reasoning</p>
        <p>Conversation memory</p>
      </div>
      <div>
        <h4>Status</h4>
        <p>Prototype for the Darukaa.Earth challenge</p>
        <p>© 2026 Darukaa.Earth</p>
      </div>
    </footer>
  );
}
