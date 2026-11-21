"""Kit UI AquaPilot AI : CSS global + composants HTML réutilisables."""
import streamlit as st

INK = "#10262C"
ATLANTIC = "#0B3C49"
LAGOON = "#0E7C8B"
FOAM = "#BFE6EA"
AMBER = "#D9A21B"
LEAK = "#C0392B"
GREEN = "#2E8B57"
TONES = {"ok": GREEN, "info": LAGOON, "warn": AMBER, "bad": LEAK}

FARM_NAV = ["💧 Irrigation", "🛡️ Evapo-Shield", "⚡ Nexus Eau-Énergie",
            "🧂 SalinityGuard", "🔁 Bourse de l'Eau", "🌦️ Météo"]
REGIONAL_NAV = ["🗺️ Vue d'ensemble", "🔎 Analyse ferme", "📊 Consommation",
                "⚡ Nexus énergie", "🔁 Bourse de l'Eau", "🧪 Évaluation du modèle"]

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700&family=Source+Sans+3:wght@400;600&display=swap');
html, body, .stApp {{ font-family: 'Source Sans 3', sans-serif; }}
h1, h2, h3, h4 {{ font-family: 'Bricolage Grotesque', sans-serif; letter-spacing: -0.01em; }}
footer, [data-testid="stDecoration"], [data-testid="stAppDeployButton"] {{ display: none !important; }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1280px; }}

/* Sidebar */
[data-testid="stSidebar"] {{ background: {ATLANTIC}; }}
[data-testid="stSidebar"] * {{ color: #E8F4F5 !important; }}
[data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,.15); }}
[data-testid="stSidebar"] .stButton > button {{ background: transparent; border: 1px solid rgba(232,244,245,.45); }}
[data-testid="stSidebar"] .stButton > button:hover {{ background: rgba(255,255,255,.1); }}

/* Menu des modules (sidebar) */
[data-testid="stSidebar"] [role="radiogroup"] {{ gap: 2px; }}
[data-testid="stSidebar"] [role="radiogroup"] label {{ padding: 8px 10px; border-radius: 8px; width: 100%; }}
[data-testid="stSidebar"] [role="radiogroup"] label:hover {{ background: rgba(255,255,255,.08); }}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {{ background: rgba(14,124,139,.6); }}

/* Hero */
.ap-hero {{ background: {ATLANTIC}; border-radius: 14px; padding: 28px 32px; margin-bottom: 22px;
  background-image: radial-gradient(1200px 300px at 100% 0%, rgba(14,124,139,.55), transparent 60%); }}
.ap-hero h1 {{ color: #fff !important; font-size: 2rem !important; margin: 0 0 6px 0 !important; padding: 0 !important; }}
.ap-hero p {{ color: {FOAM} !important; margin: 0 !important; font-size: 1.05rem; max-width: 70ch; }}
.ap-chips {{ margin-top: 14px; display: flex; gap: 8px; flex-wrap: wrap; }}
.ap-chip {{ border: 1px solid rgba(191,230,234,.45); color: {FOAM}; border-radius: 999px; padding: 3px 12px; font-size: .85rem; }}

/* KPI */
.ap-kpi {{ background: #fff; border-radius: 12px; padding: 16px 18px; border: 1px solid #DDE7E8; border-left: 5px solid var(--tone); height: 100%; }}
.ap-kpi .l {{ font-size: .9rem; color: #4B646B; }}
.ap-kpi .v {{ font-family: 'Bricolage Grotesque', sans-serif; font-size: 1.9rem; font-weight: 700; line-height: 1.15; color: {INK}; }}
.ap-kpi .d {{ font-size: .85rem; color: var(--tone); font-weight: 600; min-height: 1.1em; }}

/* Alertes */
.ap-alert {{ border-radius: 10px; padding: 12px 16px; margin: 8px 0; background: #fff; border: 1px solid #DDE7E8; border-left: 5px solid var(--tone); }}
.ap-alert b {{ color: var(--tone); }}
.ap-alert span {{ display: block; color: #3C555C; margin-top: 2px; }}

/* Badges de transparence */
.ap-badge {{ display: inline-block; font-family: 'Source Sans 3', sans-serif; font-size: .78rem; font-weight: 600; padding: 2px 10px; border-radius: 999px; vertical-align: middle; margin-left: 10px; letter-spacing: 0; }}
.ap-badge.real {{ background: #DDF1E6; color: #1E6B45; }}
.ap-badge.sim {{ background: #FBEFD0; color: #8A6410; }}
.ap-badge.mix {{ background: #DCEBF5; color: #1F5A80; }}

/* Section */
.ap-section {{ margin: 26px 0 8px 0; }}
.ap-section h3 {{ margin: 0 !important; padding: 0 !important; }}
.ap-section p {{ margin: 2px 0 0 0 !important; color: #4B646B; }}

.stButton > button, .stDownloadButton > button {{ border-radius: 10px; font-weight: 600; }}
[data-testid="stMetric"] {{ background: #fff; border: 1px solid #DDE7E8; border-radius: 12px; padding: 12px 16px; }}
@media (max-width: 700px) {{ .ap-hero {{ padding: 20px; }} .ap-hero h1 {{ font-size: 1.5rem !important; }} }}
</style>
"""

BADGES = {
    "real": '<span class="ap-badge real">Données réelles</span>',
    "sim": '<span class="ap-badge sim">Données simulées</span>',
    "mix": '<span class="ap-badge mix">Météo réelle · modèle</span>',
}


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str, chips: list[str] | None = None) -> None:
    chips_html = "".join(f'<span class="ap-chip">{c}</span>' for c in (chips or []))
    st.markdown(
        f'<div class="ap-hero"><h1>{title}</h1><p>{subtitle}</p><div class="ap-chips">{chips_html}</div></div>',
        unsafe_allow_html=True,
    )


def kpi(label: str, value: str, delta: str = "", tone: str = "info") -> None:
    st.markdown(
        f'<div class="ap-kpi" style="--tone:{TONES[tone]}"><div class="l">{label}</div>'
        f'<div class="v">{value}</div><div class="d">{delta}</div></div>',
        unsafe_allow_html=True,
    )


def alert(tone: str, title: str, body: str = "") -> None:
    st.markdown(
        f'<div class="ap-alert" style="--tone:{TONES[tone]}"><b>{title}</b><span>{body}</span></div>',
        unsafe_allow_html=True,
    )


def section(title: str, caption: str = "", source: str | None = None) -> None:
    """source : 'real', 'sim' ou 'mix' (météo réelle + modèle) -> badge de transparence."""
    cap = f"<p>{caption}</p>" if caption else ""
    st.markdown(f'<div class="ap-section"><h3>{title}{BADGES.get(source, "")}</h3>{cap}</div>',
                unsafe_allow_html=True)


LEGEND_NAMES = {
    "solaire_idx": "Solaire", "eolien_idx": "Éolien", "enr_idx": "Total ENR",
    "temp_max": "Température max", "temp_min": "Température min",
}


def style_fig(fig, height: int = 400):
    """Identité visuelle Plotly : titre en haut à gauche, légende juste sous le titre, jamais superposés."""
    fig.for_each_trace(lambda t: t.update(name=LEGEND_NAMES.get(t.name, t.name)))
    fig.update_layout(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#FFFFFF",
        font=dict(family="Source Sans 3, sans-serif", color=INK, size=14),
        colorway=[LAGOON, AMBER, LEAK, GREEN, ATLANTIC, "#7FB7BE"],
        margin=dict(l=16, r=16, t=96, b=16),
        title=dict(font=dict(family="Bricolage Grotesque, sans-serif", size=18),
                   x=0, xanchor="left", y=0.97, yanchor="top"),
        legend=dict(title_text="", orientation="h", x=0, xanchor="left", y=1.02, yanchor="bottom"),
    )
    fig.update_xaxes(gridcolor="#E4ECEC", zeroline=False)
    fig.update_yaxes(gridcolor="#E4ECEC", zeroline=False)
    return fig
