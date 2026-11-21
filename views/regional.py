import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

from ui.style import hero, kpi, alert, section, style_fig, REGIONAL_NAV
from core.anomaly import daily_features, detect, diagnose, evaluate
from core.synthetic import ensure_data
from core.network import explain, period_comparison, peak_stats, regional_profile, shift_scenario, simultaneity
import plotly.graph_objects as go

from connectors.open_meteo import fetch_forecast
from core.evapo import compute_risk
from core.nexus import regional_nexus
from core.reference import PROVINCES

from core import bourse

SATELLITE = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"

hero(
    "Dashboard régional",
    "Supervision du réseau d'eau, détection de fuites et alignement avec l'énergie renouvelable.",
    ["Compteurs simulés", "Isolation Forest", "Prévisions Open-Meteo"],
)

with st.expander("Paramètres du modèle"):
    contamination = st.slider("Part d'anomalies attendue", 0.01, 0.10, 0.03, 0.01)


@st.cache_data(show_spinner="Analyse du réseau…")
def load_analysis(contamination):
    hourly, farms = ensure_data()
    daily = detect(daily_features(hourly), contamination)
    return hourly, farms, daily

@st.cache_data(ttl=3600, show_spinner="Prévisions énergie renouvelable…")
def load_province_risk(prov):
    c = PROVINCES[prov]
    hourly_fc, _ = fetch_forecast(c["lat"], c["lon"], days=3)
    return compute_risk(hourly_fc)


hourly, farms, daily_all = load_analysis(contamination)
daily_all = daily_all.merge(farms[["farm_id", "province", "lat", "lon", "area_ha", "crop"]], on="farm_id")

all_provinces = sorted(farms["province"].unique())
provinces = st.multiselect("Provinces", all_provinces, default=all_provinces)
daily = daily_all[daily_all["province"].isin(provinces)].copy()
if daily.empty:
    st.warning("Sélectionnez au moins une province.")
    st.stop()

# Diagnostic des jours anormaux
night_ref = daily_all["ratio_nuit"].median()
daily["diagnostic"] = ""
mask = daily["anomalie"] == 1
if mask.any():
    daily.loc[mask, "diagnostic"] = daily[mask].apply(lambda r: diagnose(r, night_ref), axis=1)

# Indicateurs clés
last_day = daily["date"].max()
last30 = daily[daily["date"] > last_day - pd.Timedelta(days=30)]
recent_flagged = daily[(daily["date"] > last_day - pd.Timedelta(days=7)) & (daily["anomalie"] == 1)]

n_alert_farms = recent_flagged["farm_id"].nunique()
n_anom_30 = int(last30["anomalie"].sum())

c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi("Exploitations suivies", str(daily["farm_id"].nunique()), "", "info")
with c2:
    kpi("Volume 30 jours", f"{last30['volume_m3'].sum():,.0f} m³".replace(",", " "), "", "info")
with c3:
    kpi("Anomalies (30 jours)", str(n_anom_30), "à vérifier" if n_anom_30 else "rien à signaler",
        "warn" if n_anom_30 else "ok")
with c4:
    kpi("Fermes en alerte (7 jours)", str(n_alert_farms), "intervention conseillée" if n_alert_farms else "réseau stable",
        "bad" if n_alert_farms else "ok")

NAV = REGIONAL_NAV
nav = st.session_state.get("regional_nav", NAV[0])
st.write("")

if nav == NAV[0]:
    # Carte du réseau
    section("Carte des exploitations", "Rouge : anomalie détectée ces 7 derniers jours.", source="sim")
    fm = farms[farms["province"].isin(provinces)]
    m = folium.Map(tiles=None)
    folium.TileLayer(tiles=SATELLITE, attr="Esri World Imagery", name="Satellite").add_to(m)
    flagged = set(recent_flagged["farm_id"])
    for _, r in fm.iterrows():
        is_alert = r["farm_id"] in flagged
        folium.CircleMarker(
            [r["lat"], r["lon"]], radius=9, color="#C0392B" if is_alert else "#2E8B57",
            fill=True, fill_opacity=0.8,
            tooltip=f"{r['farm_id']} · {r['province']} · {'ALERTE' if is_alert else 'normal'}",
        ).add_to(m)
    m.fit_bounds([[fm["lat"].min() - 0.1, fm["lon"].min() - 0.1], [fm["lat"].max() + 0.1, fm["lon"].max() + 0.1]])
    st_folium(m, height=380, use_container_width=True, returned_objects=[], key="regional_map")

    # Table des anomalies
    section("Anomalies détectées", "Jours dont le profil de consommation s'écarte de la normale.", source="sim")
    an = daily[mask].sort_values("date", ascending=False)
    if an.empty:
        alert("ok", "Aucune anomalie détectée", "Sur la période et les provinces sélectionnées.")
    else:
        view = pd.DataFrame({
            "Date": an["date"].dt.strftime("%d/%m/%Y"),
            "Ferme": an["farm_id"],
            "Province": an["province"],
            "Volume (m³)": an["volume_m3"].round(0),
            "Part de nuit (%)": (an["ratio_nuit"] * 100).round(1),
            "Diagnostic": an["diagnostic"],
            "Score": an["score"].round(3),
        })
        st.dataframe(view, use_container_width=True, hide_index=True)

if nav == NAV[1]:
    # Détail d'une ferme
    section("Analyse d'une exploitation", "Consommation journalière et profil horaire d'un jour anormal.", source="sim")
    farm_id = st.selectbox("Exploitation", sorted(daily["farm_id"].unique()))
    fd = daily[daily["farm_id"] == farm_id]

    fig = px.line(fd, x="date", y="volume_m3", title=f"Consommation journalière · {farm_id} (m³)")
    fa = fd[fd["anomalie"] == 1]
    fig.add_scatter(x=fa["date"], y=fa["volume_m3"], mode="markers",
                    marker=dict(color="#C0392B", size=9), name="Anomalie détectée")
    st.plotly_chart(style_fig(fig), use_container_width=True, key="farm_daily")

    if not fa.empty:
        day = st.selectbox("Inspecter un jour anormal", list(fa["date"].dt.date),
                           format_func=lambda d: d.strftime("%d/%m/%Y"))
        hh = hourly[hourly["farm_id"] == farm_id].copy()
        hh["date"] = hh["time"].dt.normalize()
        hh["h"] = hh["time"].dt.hour
        profil = hh[hh["date"].isin(fd[fd["anomalie"] == 0]["date"])].groupby("h")["conso_m3"].mean().rename("Profil normal moyen")
        jour = hh[hh["date"] == pd.Timestamp(day)].set_index("h")["conso_m3"].rename("Jour sélectionné")
        st.plotly_chart(
            style_fig(px.line(pd.concat([profil, jour], axis=1), title="Profil horaire (m³/h)",
                              labels={"h": "Heure", "value": "m³/h", "variable": ""})),
            use_container_width=True, key="day_profile",
        )
        st.caption("Un débit élevé entre 0h et 5h, quand personne n'irrigue, est la signature d'une fuite.")

if nav == NAV[2]:
    # Évolution de la consommation
    section("Évolution de la consommation", "30 derniers jours contre les 30 précédents.", source="sim")
    cmp = period_comparison(daily).merge(farms[["farm_id", "province"]], on="farm_id")

    tot_cur, tot_prev = cmp["volume_cur"].sum(), cmp["volume_prev"].sum()
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Volume 30 jours", f"{tot_cur:,.0f} m³".replace(",", " "),
              f"{(tot_cur / tot_prev - 1) * 100:+.1f} %", delta_color="off")
    k2.metric("Volume 30 jours précédents", f"{tot_prev:,.0f} m³".replace(",", " "))
    k3.metric("Écart attribuable aux anomalies", f"{cmp['part_anomalies'].sum():+,.0f} m³".replace(",", " "))
    k4.metric("Écart « normal »", f"{cmp['part_normale'].sum():+,.0f} m³".replace(",", " "))

    st.plotly_chart(
        style_fig(px.bar(cmp.sort_values("var_m3"), x="farm_id", y="var_m3", color="province",
                         title="Variation de consommation par ferme (m³)",
                         labels={"var_m3": "Variation (m³)", "farm_id": "Ferme"})),
        use_container_width=True, key="period_bar",
    )
    table = pd.DataFrame({
        "Ferme": cmp["farm_id"], "Province": cmp["province"],
        "Volume actuel (m³)": cmp["volume_cur"].round(0), "Volume précédent (m³)": cmp["volume_prev"].round(0),
        "Variation (%)": cmp["var_pct"].round(1),
        "Part de nuit actuelle (%)": cmp["nuit_cur_pct"].round(1),
        "Part de nuit précédente (%)": cmp["nuit_prev_pct"].round(1),
        "Explication": cmp["explication"],
    }).sort_values("Variation (%)", ascending=False)
    st.dataframe(table, use_container_width=True, hide_index=True)
    st.caption(
        "Décomposition heuristique : la part « anomalies » est le volume au-dessus de la normale les jours signalés par "
        "Isolation Forest ; le reste regroupe saison, climat et cultures (une jointure avec l'ET₀ NASA POWER permettrait "
        "de les séparer)."
    )

    # Simultanéité des irrigations
    section("Simultanéité des irrigations", "Combien de fermes irriguent en même temps, et que gagne-t-on à étaler la demande.", source="sim")
    prov = st.selectbox("Province analysée", provinces, key="sim_prov")
    ids = farms[farms["province"] == prov]["farm_id"]
    profile = regional_profile(hourly, ids)
    stats = peak_stats(profile)
    sim = simultaneity(hourly, ids)

    shift = st.slider("Part des volumes de pointe décalée vers la nuit (22h à 6h)", 0, 50, 20, 5) / 100
    scenario = shift_scenario(profile, shift)
    reduction = (1 - scenario.max() / profile.max()) * 100

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Heure de pointe", f"{stats['heure_pointe']}h")
    s2.metric("Facteur de pointe", f"{stats['facteur_pointe']:.1f}")
    s3.metric("Fermes actives à la pointe", f"{sim.loc[stats['heure_pointe']] * 100:.0f} %")
    s4.metric("Pic après décalage", f"{scenario.max():.0f} m³/h", f"-{reduction:.0f} %", delta_color="inverse")

    curves = pd.concat([profile.rename("Actuel"), scenario.rename("Après décalage")], axis=1)
    st.plotly_chart(
        style_fig(px.line(curves, labels={"h": "Heure", "value": "m³/h", "variable": ""},
                          title=f"Charge horaire médiane · {prov}")),
        use_container_width=True, key="sim_profile",
    )
    st.caption(
        "Un facteur de pointe élevé signifie que le réseau doit être dimensionné pour quelques heures seulement. "
        "Ici les compteurs sont simulés avec un profil commun : la forte simultanéité est donc attendue par construction. "
        "Sur de vraies données, elle indiquerait où étaler la demande (et réduire le coût de pompage, cf. Nexus)."
    )

if nav == NAV[3]:
    # Nexus Eau-Énergie régional
    section("Nexus Eau-Énergie régional", "Alignement du pompage avec la production solaire et éolienne prévue.", source="mix")
    flex = st.slider("Part de la demande de pompage déplaçable (stockage)", 0, 60, 30, 5, key="nexus_flex") / 100

    results = {}
    cols = st.columns(len(provinces))
    for col, prov in zip(cols, provinces):
        ids = farms[farms["province"] == prov]["farm_id"]
        try:
            risk = load_province_risk(prov)
        except Exception as e:
            col.warning(f"{prov} : prévisions indisponibles ({e})")
            continue
        res = regional_nexus(regional_profile(hourly, ids), risk, flex)
        results[prov] = res
        n, s = res["now"], res["scen"]

        ref = res["reference"]
        top = int(min(100, max(30, round(max(res["scen"]["alignement"], ref) * 2 / 10) * 10)))
        fig = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=n["alignement"],
            number={"suffix": " %"},
            delta={"reference": res["reference"], "valueformat": ".0f"},
            title={"text": prov},
            gauge={
                "axis": {"range": [0, top]},
                "bar": {"color": "#0E7C8B"},
                "threshold": {"line": {"color": "black", "width": 3}, "value": ref},
                "steps": [
                    {"range": [0, ref], "color": "#F8D7DA"},
                    {"range": [ref, min(top, ref * 1.5)], "color": "#FFF3CD"},
                    {"range": [min(top, ref * 1.5), top], "color": "#D4EDDA"},
                ],
            },
        ))
        fig.update_layout(height=230, margin=dict(l=20, r=20, t=50, b=10),
                          paper_bgcolor="rgba(0,0,0,0)", font=dict(family="Source Sans 3, sans-serif"))
        col.plotly_chart(fig, use_container_width=True, key=f"nexus_gauge_{prov}")
        col.metric("Coût de pompage / jour", f"{n['cout']:.0f} MAD")
        col.metric("Avec pompage vert", f"{s['cout']:.0f} MAD", f"{s['cout'] - n['cout']:+.0f} MAD", delta_color="inverse")
        col.caption(f"Alignement : {n['alignement']:.0f} % → {s['alignement']:.0f} % · {res['kwh_deplaces']:.0f} kWh déplacés")

    if results:
        tot_now = sum(r["now"]["cout"] for r in results.values())
        tot_scen = sum(r["scen"]["cout"] for r in results.values())
        kwh_moved = sum(r["kwh_deplaces"] for r in results.values())
        t1, t2, t3 = st.columns(3)
        t1.metric("Coût régional / jour", f"{tot_now:.0f} MAD")
        t2.metric("Avec pompage vert", f"{tot_scen:.0f} MAD",
                  f"{(tot_scen / tot_now - 1) * 100:+.1f} %" if tot_now else None, delta_color="inverse")
        t3.metric("Énergie déplacée vers les heures ENR", f"{kwh_moved:.0f} kWh/jour")

        pick = st.selectbox("Détail d'une province", list(results), key="nexus_pick")
        det = results[pick]["detail"]
        fig2 = go.Figure()
        fig2.add_scatter(x=det.index, y=det["actuel"], name="Demande actuelle (m³/h)")
        fig2.add_scatter(x=det.index, y=det["pompage_vert"], name="Après pompage vert (m³/h)")
        fig2.add_scatter(x=det.index, y=det["enr_idx"], name="Indice ENR (0 à 1)", yaxis="y2", line=dict(dash="dot"))
        fig2.update_layout(
            title=f"Demande de pompage et énergie renouvelable · {pick}",
            xaxis_title="Heure", yaxis_title="m³/h",
            yaxis2=dict(overlaying="y", side="right", range=[0, 1], title="Indice ENR"),
        )
        st.plotly_chart(style_fig(fig2), use_container_width=True, key="nexus_detail")
        hrs = ", ".join(f"{h}h" for h in results[pick]["heures"]) or "aucune"
        st.caption(
            f"Heures recommandées pour le pompage déplaçable : {hrs}. "
            "Hypothèses : prix dynamique du kWh et tarif de base provisoires ; la part déplaçable suppose un stockage "
            "(bassins), car l'irrigation elle-même reste pilotée par Evapo-Shield ; indices ENR = proxies de potentiel, "
            "pas la production réelle du réseau."
        )

if nav == NAV[4]:
    # Bourse de l'Eau : supervision
    section("Bourse de l'Eau · supervision", "Tokens en circulation, prix et transactions entre agriculteurs.", source="sim")
    bstate = bourse.load()
    brules = bstate["rules"]
    names = {k: v["name"] for k, v in bstate["accounts"].items()}
    trades = pd.DataFrame([t for t in bstate["transactions"] if t["type"] == "trade"])

    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Tokens en circulation", f"{bourse.total_tokens(bstate):,}".replace(",", " "))
    b2.metric("Tokens proposés à la vente", sum(o["qty"] for o in bstate["offers"]))
    if trades.empty:
        b3.metric("Volume échangé", "0 m³")
        b4.metric("Prix moyen pondéré", "n/a")
    else:
        vol = int(trades["qty"].sum())
        avg = float((trades["qty"] * trades["price"]).sum() / vol)
        b3.metric("Volume échangé", f"{vol} m³")
        b4.metric("Prix moyen pondéré", f"{avg:.2f} MAD", f"{avg - brules['prix_ref']:+.2f} vs référence", delta_color="off")

    r1, r2, r3 = st.columns([1, 1, 1])
    new_ref = r1.number_input("Prix de référence (MAD/token)", min_value=0.1, value=float(brules["prix_ref"]),
                              step=0.1, key="rule_ref")
    new_cap = r2.number_input("Prix plafond (MAD/token)", min_value=0.1, value=float(brules["prix_plafond"]),
                              step=0.1, key="rule_cap")
    r3.write("")
    r3.write("")
    if r3.button("Enregistrer les règles", key="rule_save"):
        ok, msg = bourse.update_rules(bstate, new_ref, new_cap)
        if ok:
            bourse.save(bstate)
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)

    if bstate["offers"]:
        st.markdown("**Offres ouvertes**")
        st.dataframe(pd.DataFrame([{
            "Province": o["province"], "Vendeur": names[o["seller"]], "Tokens": o["qty"], "Prix (MAD)": o["price"],
            "Alerte": "Au-dessus du plafond" if o["price"] > brules["prix_plafond"] else "",
        } for o in bstate["offers"]]), use_container_width=True, hide_index=True)

    if trades.empty:
        st.caption("Aucun échange pour le moment. Connectez-vous en tant qu'agriculteur pour en créer.")
    else:
        st.markdown("**Transactions**")
        tx = pd.DataFrame({
            "Date": trades["time"].str.replace("T", " "),
            "Province": trades["province"],
            "Vendeur": trades["seller"].map(names),
            "Acheteur": trades["buyer"].map(names),
            "Tokens": trades["qty"],
            "Prix (MAD)": trades["price"],
            "Total (MAD)": (trades["qty"] * trades["price"]).round(0),
            "Alerte": ["Prix > 125 % de la référence" if p > 1.25 * brules["prix_ref"] else "" for p in trades["price"]],
        }).iloc[::-1]
        st.dataframe(tx, use_container_width=True, hide_index=True)
        by_prov = trades.groupby("province")["qty"].sum().reset_index()
        st.plotly_chart(style_fig(px.bar(by_prov, x="province", y="qty", title="Volume échangé par province (m³)",
                                         labels={"qty": "m³", "province": "Province"})),
                        use_container_width=True, key="bourse_volume")

    with st.expander("Zone de démonstration"):
        st.caption("Remet les soldes, offres et transactions à leur état de départ.")
        if st.checkbox("Confirmer la réinitialisation", key="bourse_reset_ok") and st.button("Réinitialiser la Bourse", key="bourse_reset"):
            bourse.reset()
            st.rerun()


if nav == NAV[5]:
    # Évaluation
    with st.expander("Évaluation du modèle (sur données simulées)"):
        ev = evaluate(daily_all)
        e1, e2, e3 = st.columns(3)
        e1.metric("Précision", f"{ev['precision'] * 100:.0f} %")
        e2.metric("Rappel", f"{ev['rappel'] * 100:.0f} %")
        e3.metric("F1", f"{ev['f1'] * 100:.0f} %")
        st.write(f"Vrais positifs : {ev['tp']} · Faux positifs : {ev['fp']} · Fuites manquées : {ev['fn']} · Vrais négatifs : {ev['tn']}")
        st.caption(
            "Ces scores sont mesurés sur des fuites que nous avons nous-mêmes injectées : ils sont optimistes. "
            "Sur un vrai réseau, chaque alerte devrait être confirmée sur le terrain.")
        st.markdown("**Qualité du diagnostic** (type réel en lignes, diagnostic du système en colonnes)")
        det = daily_all[(daily_all["anomalie"] == 1) & (daily_all["fuite_reelle"] == 1)].copy()
        if not det.empty:
            det["diagnostic"] = det.apply(lambda r: diagnose(r, night_ref), axis=1)
            st.dataframe(pd.crosstab(det["type_evenement"], det["diagnostic"]), use_container_width=True)
