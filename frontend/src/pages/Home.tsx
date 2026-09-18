import { useNavigate } from "react-router-dom";
import { APP_NAME } from "../brand";

const FOREST =
  "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?auto=format&fit=crop&w=1600&q=80";
const LAKE =
  "https://images.unsplash.com/photo-1501785888041-af3ef285b470?auto=format&fit=crop&w=900&q=80";
const ICE =
  "https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?auto=format&fit=crop&w=900&q=80";
const PEOPLE =
  "https://images.unsplash.com/photo-1469474968028-56623f02e42e?auto=format&fit=crop&w=900&q=80";
const TURTLE =
  "https://images.unsplash.com/photo-1437622368342-7a3d73a34c8f?auto=format&fit=crop&w=900&q=80";
const FARM =
  "https://images.unsplash.com/photo-1500382017468-9049fed747ef?auto=format&fit=crop&w=900&q=80";

export function Home() {
  const navigate = useNavigate();
  return (
    <main>
      <section className="hero">
        <div>
          <p className="kicker">Together for a living planet</p>
          <h1>
            Read the land.
            <br />
            Restore what remains.
          </h1>
          <p className="lede">
            {APP_NAME} is an AI environmental scientist. It retrieves scientific evidence, reasons across soil,
            water, habitat and climate together, and will not invent papers to fill the silence.
          </p>
          <div className="hero-actions">
            <button className="btn primary" onClick={() => navigate("/lab")}>
              Ask the scientist →
            </button>
            <button className="btn ghost" onClick={() => navigate("/knowledge")}>
              Browse knowledge
            </button>
          </div>
          <p className="tiny">Join a conversation that remembers your soil carbon, rainfall and land use.</p>
        </div>
        <div className="hero-visual">
          <img src={FOREST} alt="Forest canopy meeting dry land" />
          <div className="float-card" style={{ top: 28 }}>
            <b>Soil carbon</b>
            <span>Tracked as a living metric, not a slogan.</span>
          </div>
          <div className="float-card" style={{ top: 128 }}>
            <b>Habitat</b>
            <span>Monoculture vs corridors, with sources.</span>
          </div>
          <div className="float-card" style={{ top: 228 }}>
            <b>Evidence</b>
            <span>Every claim keeps its document and page.</span>
          </div>
        </div>
      </section>

      <section className="stats">
        <div className="stat">
          <strong>8+</strong>
          Seed scientific syntheses
        </div>
        <div className="stat">
          <strong>3+</strong>
          Variables reasoned together
        </div>
        <div className="stat">
          <strong>RAG</strong>
          Real retrieval, not prompt stuffing
        </div>
        <div className="stat">
          <strong>None</strong>
          Invented citations allowed
        </div>
      </section>

      <section className="section cream-card">
        <div className="split">
          <div>
            <p className="kicker">Our method</p>
            <h2>
              Greener reasoning.
              <br />
              Cleaner evidence.
              <br />
              Stronger advice.
            </h2>
            <p className="lede">
              If biodiversity is declining on a farm, the system asks for soil organic carbon, rainfall and land use
              before it recommends cover crops or agroforestry. Then it shows the passages it used.
            </p>
            <div className="pill-row">
              <span className="pill">Soil health</span>
              <span className="pill">Water stress</span>
              <span className="pill">Habitat</span>
              <span className="pill">Human impact</span>
            </div>
          </div>
          <div className="photo-grid">
            <img src={LAKE} alt="Lake and forest" />
            <img src={ICE} alt="Climate landscape" />
            <img src={PEOPLE} alt="Living landscape" />
          </div>
        </div>
      </section>

      <section className="section">
        <p className="kicker">What it can investigate</p>
        <h2>Real pressures. Specific interventions.</h2>
        <div className="photo-grid">
          <article className="photo-card">
            <img src={TURTLE} alt="Ocean and wildlife" />
            <h3>Pollution and urban edge</h3>
            <p>Buffers, corridors and source control when species richness is already falling.</p>
          </article>
          <article className="photo-card">
            <img src={FOREST} alt="Forest remnants" />
            <h3>Fragmented forests</h3>
            <p>Reconnect remnants instead of planting another monoculture.</p>
          </article>
          <article className="photo-card">
            <img src={FARM} alt="Farm landscape" />
            <h3>Dryland wheat country</h3>
            <p>Low SOC + low rain + monoculture → cover, residue and spaced trees.</p>
          </article>
        </div>
      </section>
    </main>
  );
}
