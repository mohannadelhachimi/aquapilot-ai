import pandas as pd
from datetime import date, timedelta
import folium
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

from ui.style import hero, kpi, alert, section, style_fig, FARM_NAV
from connectors.nasa_power import fetch_daily
from connectors.open_meteo import fetch_forecast
from core.geo import distance_km
from core.reference import CROPS, IRRIGATION, PROVINCES, WATER_SOURCES
from core.storage import get_farm, save_farm
from core.agro import irrigation_plan, scenarios
from core.evapo import BLOCK_THRESHOLD, compute_risk, shield_status
from core.nexus import nexus_plan

import plotly.graph_objects as go

from connectors.climatology import fetch_et0_climatology
from core.salinity import compare_scenarios, recommendations

from core import bourse

SATELLITE = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"

user = st.session_state["user"]
farm = get_farm(user["username"])

if "editing" not in st.session_state:
    st.session_state["editing"] = farm is None


def make_map(lat, lon, height_zoom=12):
    m = folium.Map(location=[lat, lon], zoom_start=height_zoom, tiles=None)
    folium.TileLayer(tiles=SATELLITE, attr="Esri World Imagery", name="Satellite").add_to(m)
    folium.Marker([lat, lon], tooltip="Votre parcelle", icon=folium.Icon(color="blue", icon="tint")).add_to(m)
    return m


def location_picker(province, existing):
    center = PROVINCES[province]

    # Réinitialise le point quand la province change
    if st.session_state.get("pin_province") != province:
        same = existing.get("province") == province and "lat" in existing
        st.session_state["pin_province"] = province
        st.session_state["pin_lat"] = existing["lat"] if same else center["lat"]
        st.session_state["pin_lon"] = existing["lon"] if same else center["lon"]

    st.markdown("**Localisation de la parcelle** : cliquez sur la carte à l'emplacement de votre exploitation.")
    out = st_folium(
        make_map(st.session_state["pin_lat"], st.session_state["pin_lon"]),
        height=420, use_container_width=True,
        returned_objects=["last_clicked"], key="pin_map",
    )

    click = out.get("last_clicked") if out else None
    if click:
        point = (round(click["lat"], 6), round(click["lng"], 6))
        if point != st.session_state.get("last_click_seen"):
            st.session_state["last_click_seen"] = point
            st.session_state["pin_lat"], st.session_state["pin_lon"] = point
            st.rerun()

    c1, c2 = st.columns(2)
    c1.number_input("Latitude", key="pin_lat", min_value=-90.0, max_value=90.0, format="%.6f", step=0.0001)
    c2.number_input("Longitude", key="pin_lon", min_value=-180.0, max_value=180.0, format="%.6f", step=0.0001)
    lat, lon = st.session_state["pin_lat"], st.session_state["pin_lon"]

    if distance_km(lat, lon, center["lat"], center["lon"]) > 150:
        alert("warn", "Position éloignée de la province",
              f"Ce point semble à plus de 150 km de {province}. Vérifiez la province ou la position.")
    return lat, lon


def config_form(existing):
    existing = existing or {}
    provinces = list(PROVINCES)
    crops = list(CROPS)
    irrigations = list(IRRIGATION)

    section("Configuration de l'exploitation",
            "Ces informations personnalisent les recommandations selon votre province, votre culture et votre parcelle.")

    c1, c2 = st.columns(2)
    province = c1.selectbox(
        "Province", provinces,
        index=provinces.index(existing.get("province", user.get("province", provinces[0]))),
    )
    crop = c2.selectbox("Culture", crops, index=crops.index(existing.get("crop", crops[0])))

    lat, lon = location_picker(province, existing)

    c3, c4 = st.columns(2)
    area = c3.number_input("Superficie (hectares)", min_value=0.1, max_value=500.0,
                           value=float(existing.get("area_ha", 2.0)), step=0.5)
    irrigation = c4.selectbox("Système d'irrigation", irrigations,
                              index=irrigations.index(existing.get("irrigation", irrigations[0])))

    c5, c6 = st.columns(2)
    source = c5.selectbox("Source d'eau", WATER_SOURCES,
                          index=WATER_SOURCES.index(existing.get("water_source", WATER_SOURCES[0])))
    ec_water = c6.number_input(
        "Salinité de l'eau (CE, dS/m)", min_value=0.1, max_value=15.0,
        value=float(existing.get("ec_water", 1.0)), step=0.1,
        help="Repères : eau dessalée traitée ≈ 0,3 à 1 ; eau de nappe saumâtre ≈ 3 à 8.",
    )
    c7, c8 = st.columns(2)
    planting = c7.date_input(
        "Date de plantation",
        value=date.fromisoformat(existing.get("planting_date", date.today().isoformat())),
    )
    ece_soil = c8.number_input(
        "CE initiale du sol (dS/m)", min_value=0.1, max_value=20.0,
        value=float(existing.get("ece_soil", 1.5)), step=0.1,
        help="Conductivité électrique du sol, mesurée par un capteur ou un laboratoire. Sans mesure, 1,5 correspond à un sol peu salé.",
    )

    if st.button("Enregistrer l'exploitation", type="primary"):
        save_farm(user["username"], {
            "province": province,
            "lat": lat,
            "lon": lon,
            "crop": crop,
            "area_ha": area,
            "irrigation": irrigation,
            "water_source": source,
            "ec_water": ec_water,
            "ece_soil": ece_soil,
            "planting_date": planting.isoformat(),
        })
        for key in ("pin_province", "pin_lat", "pin_lon"):
            st.session_state.pop(key, None)
        st.session_state["editing"] = False
        st.rerun()


def farm_coords(f):
    base = PROVINCES[f["province"]]
    return f.get("lat", base["lat"]), f.get("lon", base["lon"])


@st.cache_data(ttl=3600, show_spinner="Récupération des prévisions…")
def load_forecast(lat, lon):
    return fetch_forecast(lat, lon, days=7)


@st.cache_data(ttl=86400, show_spinner="Récupération de l'historique NASA POWER…")
def load_history(lat, lon, start, end):
    return fetch_daily(lat, lon, start, end)


def weather_section(f):
    lat, lon = farm_coords(f)
    section(f"Conditions météorologiques · {f['province']}", "Prévisions Open-Meteo et historique NASA POWER.", source="real")
    tab_forecast, tab_history = st.tabs(["Prévisions 7 jours", "Historique 90 jours"])

    with tab_forecast:
        try:
            hourly, daily = load_forecast(lat, lon)
        except Exception as e:
            st.warning(f"Prévisions indisponibles pour le moment ({e}).")
        else:
            today = daily.iloc[0]
            c1, c2, c3 = st.columns(3)
            c1.metric("Température max aujourd'hui", f"{today['temp_max']:.1f} °C")
            c2.metric("ET₀ prévue aujourd'hui", f"{today['et0_mm']:.1f} mm")
            c3.metric("Vent max (7 j)", f"{hourly['vent_ms'].max():.1f} m/s")
            st.plotly_chart(style_fig(px.line(hourly, x="time", y="temp", title="Température (°C)")),
                            use_container_width=True)
            st.plotly_chart(style_fig(px.line(hourly, x="time", y="vent_ms", title="Vent (m/s)")),
                            use_container_width=True)

    with tab_history:
        end = date.today() - timedelta(days=5)  # NASA POWER publie avec quelques jours de retard
        start = end - timedelta(days=90)
        try:
            hist = load_history(lat, lon, start, end)
        except Exception as e:
            st.warning(f"Historique NASA POWER indisponible ({e}).")
        else:
            st.plotly_chart(style_fig(px.line(hist, y=["temp_max", "temp_min"], title="Températures (°C)")),
                            use_container_width=True)
            st.plotly_chart(style_fig(px.line(hist, y="vent_ms", title="Vent moyen (m/s)")),
                            use_container_width=True)
            st.caption("Source : NASA POWER (données observées / réanalyse).")

def irrigation_section(f):
    lat, lon = farm_coords(f)
    section("Planification de l'irrigation", "Besoins en eau des 7 prochains jours, selon la culture et la météo.", source="mix")
    try:
        _, daily = load_forecast(lat, lon)
    except Exception as e:
        st.warning(f"Calcul impossible sans prévisions ({e}).")
        return

    plan = irrigation_plan(daily, f)
    today = plan.iloc[0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Stade actuel", today["stade"])
    c2.metric("Kc du jour", f"{today['kc']:.2f}")
    c3.metric("Volume aujourd'hui", f"{today['volume_m3']:.0f} m³")
    c4.metric("Volume 7 jours", f"{plan['volume_m3'].sum():.0f} m³")

    st.plotly_chart(
        style_fig(px.bar(plan, x="date", y="volume_m3", title="Volume d'irrigation recommandé (m³/jour)")),
        use_container_width=True,
    )

    with st.expander("Détail du calcul jour par jour"):
        st.dataframe(plan, use_container_width=True, hide_index=True)

    st.markdown("**Comparaison de scénarios (7 prochains jours)**")
    sc = scenarios(plan, f)
    st.dataframe(sc, use_container_width=True, hide_index=True)
    st.caption(
        "Estimation du modèle : l'économie est calculée à partir du rendement théorique de chaque système "
        "(goutte-à-goutte 90 %, aspersion 75 %, gravitaire 60 %), pas à partir de mesures sur le terrain."
    )

def evapo_section(f):
    lat, lon = farm_coords(f)
    section("Evapo-Shield AI · bouclier anti-évaporation", "Bloque l'irrigation quand le vent et la chaleur font perdre l'eau.", source="mix")
    try:
        hourly, _ = load_forecast(lat, lon)
    except Exception as e:
        st.warning(f"Evapo-Shield indisponible sans prévisions ({e}).")
        return

    risk = compute_risk(hourly)
    if risk.empty:
        st.warning("Prévisions horaires périmées, rechargez la page.")
        return
    s = shield_status(risk, f["irrigation"])

    if s["bloque"]:
        alert("bad", "Irrigation bloquée", s["message"])
    else:
        alert("ok", "Irrigation autorisée", s["message"])
    if s["chergui_at"] is not None:
        alert("warn", "Chergui annoncé", f"Vent sec détecté dans les prévisions à partir du {s['chergui_at']:%d/%m à %Hh}.")

    c1, c2, c3 = st.columns(3)
    c1.metric("Risque actuel", f"{s['risque_now']:.0f} / 100")
    c1.caption(f"Niveau : {s['niveau']}")
    c2.metric("Statut", "Bloquée" if s["bloque"] else "Autorisée")
    delta = None
    if s["perte_best"] is not None:
        delta = f"{s['perte_best'] - s['perte_now']:+.1f} pt au meilleur créneau"
    c3.metric(
        "Pertes si j'irrigue maintenant", f"{s['perte_now']:.1f} %",
        delta, delta_color="inverse",
        help=f"Perte maximale supposée pour ce système : {s['max_loss']} % (hypothèse du modèle).",
    )

    fig = px.area(risk, x="time", y="risque", title="Risque d'évaporation (48 prochaines heures)")
    fig.add_hline(y=BLOCK_THRESHOLD, line_dash="dash", annotation_text="Seuil de blocage")
    if s["fenetres"]:
        best = s["fenetres"][0]
        fig.add_vrect(x0=best["debut"].to_pydatetime(), x1=best["fin"].to_pydatetime(),
                      fillcolor="green", opacity=0.25, line_width=0)
    fig.update_yaxes(range=[0, 100])
    st.plotly_chart(style_fig(fig), use_container_width=True, key="evapo_risk")

    if s["fenetres"]:
        st.markdown("**Meilleurs créneaux d'irrigation (3 h)**")
        table = pd.DataFrame([{
            "Début": w["debut"].strftime("%a %d/%m %Hh"),
            "Fin": w["fin"].strftime("%Hh"),
            "Risque moyen /100": w["risque_moyen"],
        } for w in s["fenetres"]])
        st.dataframe(table, use_container_width=True, hide_index=True)

    with st.expander("Méthode et hypothèses"):
        st.markdown(
            "- Demande évaporative = (1 + 0,5 × vent) × déficit de pression de vapeur (VPD).\n"
            "- Score normalisé de 0 à 100, blocage au-delà de 60.\n"
            "- Chergui : vent d'est, ≥ 30 °C, humidité ≤ 30 %, vent ≥ 4 m/s.\n"
            "- Pertes maximales supposées : aspersion 25 % (haut de la fourchette de 2 à 23 % mesurée sur le terrain), "
            "goutte-à-goutte 5 % et gravitaire 15 % (hypothèses du modèle, à calibrer avec des mesures terrain)."
        )

def nexus_section(f):
    lat, lon = farm_coords(f)
    section("Nexus Eau-Énergie · pompage vert", "Choisit le créneau où l'énergie renouvelable est la plus abondante.", source="mix")
    try:
        hourly, daily = load_forecast(lat, lon)
    except Exception as e:
        st.warning(f"Nexus indisponible sans prévisions ({e}).")
        return

    risk = compute_risk(hourly)
    volume = float(irrigation_plan(daily, f).iloc[0]["volume_m3"])
    if volume <= 0:
        st.info("Aucun besoin d'irrigation aujourd'hui : rien à optimiser.")
        return

    res = nexus_plan(risk, volume)
    if res["best"] is None:
        alert("bad", "Aucun créneau disponible", "Aucun créneau compatible avec Evapo-Shield dans les prochaines 24 h.")
        return

    best, ref = res["best"], res["ref"]
    slot = f"{best['debut']:%Hh%M} à {best['fin']:%Hh%M}"
    if best["debut"] != ref["debut"]:
        alert(
            "ok", f"Pompez entre {slot}",
            f"Énergie renouvelable plus abondante : coût de pompage réduit de "
            f"{res['saving_pct']:.0f} % par rapport à un pompage immédiat (estimation du modèle).",
        )
    else:
        alert("info", "Pomper maintenant est optimal", "C'est déjà le meilleur créneau des prochaines 24 h.")

    c1, c2, c3 = st.columns(3)
    c1.metric("Volume à pomper aujourd'hui", f"{volume:.0f} m³")
    c2.metric("Coût si pompage immédiat", f"{ref['cout_mad']:.0f} MAD")
    c3.metric("Coût au créneau optimal", f"{best['cout_mad']:.0f} MAD",
              f"-{res['saving_pct']:.0f} %", delta_color="inverse")

    d = res["horaire"]
    fig = px.line(d, x="time", y=["solaire_idx", "eolien_idx", "enr_idx"],
                  title="Disponibilité d'énergie renouvelable (0 à 1)")
    fig.add_vrect(x0=best["debut"].to_pydatetime(), x1=best["fin"].to_pydatetime(),
                  fillcolor="green", opacity=0.25, line_width=0,
                  annotation_text="Créneau optimal", annotation_position="top left")
    st.plotly_chart(style_fig(fig), use_container_width=True, key="nexus_enr")
    st.plotly_chart(style_fig(px.line(d, x="time", y="prix_mad_kwh", title="Prix simulé du kWh (MAD)")),
                    use_container_width=True, key="nexus_price")

    with st.expander("Méthode et hypothèses"):
        st.markdown(
            "- Indice solaire = rayonnement ÷ 900 W/m². Indice éolien = courbe de puissance simplifiée "
            "(3 m/s démarrage, 12 m/s pleine puissance, 25 m/s arrêt) sur le vent à 100 m.\n"
            "- Prix simulé = tarif de base × (1,25 − 0,5 × indice ENR) : **hypothèse de tarification dynamique**, "
            "qui n'existe pas dans la grille tarifaire actuelle.\n"
            "- Tarif de base et caractéristiques de pompage : valeurs provisoires à remplacer par des données sourcées.\n"
            "- Le volume journalier est supposé pompé en un seul créneau de 3 h."
        )

@st.cache_data(ttl=7 * 86400, show_spinner="Climatologie locale…")
def load_climatology(lat, lon):
    return fetch_et0_climatology(lat, lon)


def salinity_section(f):
    lat, lon = farm_coords(f)
    ece0 = float(f.get("ece_soil", 1.5))
    thr = CROPS[f["crop"]]["ece_seuil"]
    section("SalinityGuard · risque de salinisation", "Évolution du sel dans le sol sur la saison et lessivage conseillé.", source="mix")

    try:
        clim = load_climatology(round(lat, 2), round(lon, 2))
    except Exception as e:
        st.warning(f"Climatologie indisponible pour le moment ({e}).")
        return

    table, sims, summ, lf_rec, unsuitable = compare_scenarios(f, clim, ece0)
    none, rec = summ["Sans lessivage"], summ["Lessivage recommandé"]

    if unsuitable:
        alert(
            "bad", "Eau trop chargée en sel pour cette culture",
            f"CE de l'eau {f['ec_water']} dS/m, seuil du sol {thr} : "
            "un lessivage de 40 % ne suffit pas selon la formule FAO. Mélangez-la avec de l'eau dessalée ou changez de culture.",
        )
    elif none["perte_pct"] >= 10:
        alert(
            "bad", f"Perte de rendement estimée à {none['perte_pct']:.0f} % sans lessivage",
            f"Avec {lf_rec * 100:.0f} % de lessivage : {rec['perte_pct']:.0f} %.",
        )
    elif none["ece_fin"] > thr:
        alert(
            "warn", "Sol au-dessus du seuil en fin de saison",
            f"Sans lessivage, la CE du sol finit à {none['ece_fin']:.1f} dS/m, au-dessus du seuil de la culture ({thr}). "
            f"Pas de perte sur ce cycle selon le modèle, mais au moins {none['perte_suivante_pct']:.0f} % de perte "
            "si la saison suivante démarrait à ce niveau.",
        )
    else:
        alert("ok", "Salinité maîtrisée", "La salinité du sol reste sous le seuil de la culture sur toute la saison.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("CE du sol au départ", f"{ece0:.1f} dS/m")
    c2.metric("CE fin de saison (sans lessivage)", f"{none['ece_fin']:.1f} dS/m")
    c3.metric("Seuil de la culture", f"{thr} dS/m")
    c4.metric("Perte de rendement (sans lessivage)", f"{none['perte_pct']:.0f} %")

    fig = go.Figure()
    for name, df in sims.items():
        fig.add_scatter(x=df["date"], y=df["ece"], name=name, mode="lines")
    fig.add_hline(y=thr, line_dash="dash", line_color="red", annotation_text="Seuil de la culture")
    fig.add_hline(y=0.8 * thr, line_dash="dot", line_color="orange", annotation_text="Alerte (80 %)")
    fig.update_layout(title="CE du sol sur la saison (dS/m)", xaxis_title="Date", yaxis_title="dS/m")
    st.plotly_chart(style_fig(fig), use_container_width=True, key="salinity_curve")

    st.markdown("**Comparaison des scénarios de lessivage**")
    st.dataframe(table, use_container_width=True, hide_index=True)
    st.caption(
        "Compromis central : lessiver protège le sol mais consomme de l'eau supplémentaire, ce qui compte "
        "dans des provinces où l'eau est dessalée et chère."
    )

    st.markdown("**Recommandations sur la saison**")
    recs = recommendations(f, summ, ece0, lf_rec, unsuitable)
    tabs = st.tabs(list(recs))
    for tab, items in zip(tabs, recs.values()):
        with tab:
            for it in items:
                st.markdown(f"- {it}")

    with st.expander("Méthode et hypothèses"):
        st.markdown(
            "- Bilan de sel journalier dans la zone racinaire : le sel entre avec l'irrigation et ne sort qu'avec l'eau "
            "drainée ; l'évapotranspiration, elle, concentre le sel.\n"
            "- Météo : année type (ET₀ et pluie moyennes par jour) tirée de l'archive Open-Meteo.\n"
            "- Hypothèses : sol limoneux, profondeur racinaire par culture, ECe ≈ 0,5 × CE de la solution du sol, "
            "tolérance au sel de type FAO-29. Ordres de grandeur à calibrer avec des mesures de CE sur le terrain.\n"
            "- Modèle mécaniste (pas de machine learning) : calibrable avec des mesures réelles. "
            "Le lessivage recommandé suit la formule FAO ; notre modèle est un peu moins exigeant qu'elle."
        )

def bourse_section(f):
    section("Bourse de l'Eau · Water Tokens", "Gagnez des tokens en économisant votre quota, puis échangez-les entre agriculteurs.", source="sim")
    username = user["username"]
    state = bourse.load()
    changed = bourse.ensure_account(state, username, f["province"], user["name"])
    acc = state["accounts"][username]
    if acc["province"] != f["province"]:  # resynchronise avec la ferme enregistrée
        acc["province"] = f["province"]
        for o in state["offers"]:
            if o["seller"] == username:
                o["province"] = f["province"]
        changed = True
    if changed:
        bourse.save(state)

    flash = st.session_state.pop("bourse_msg", None)
    if flash:
        (st.success if flash[0] else st.error)(flash[1])

    rules = state["rules"]
    quota = bourse.quota_m3(state, f["province"], f["area_ha"])
    month = bourse.previous_month()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Solde de tokens", f"{acc['balance']}")
    c2.metric("Quota mensuel", f"{quota:,.0f} m³".replace(",", " "))
    c3.metric("Prix de référence", f"{rules['prix_ref']:.2f} MAD")
    c4.metric("Prix plafond", f"{rules['prix_plafond']:.2f} MAD")
    st.caption("1 token = 1 m³ économisé. Valeurs de quota et de prix provisoires, fixées par l'administration.")

    with st.expander(f"Clôture du mois {month}", expanded=month not in acc["closed_months"]):
        if month in acc["closed_months"]:
            st.info(f"Le mois {month} est déjà clôturé.")
        else:
            reading = st.number_input(
                "Consommation relevée au compteur (m³)", min_value=0.0, step=50.0, key="bourse_reading",
                value=float(bourse.simulated_reading(username, month, quota)),
                help="Valeur simulée pour la démo, modifiable. En production : relevé du compteur.",
            )
            pct = (quota - reading) / quota * 100
            seuil = rules["seuil_economie"] * 100
            st.caption(f"Économie : {pct:.0f} % du quota (seuil pour gagner des tokens : {seuil:.0f} %).")
            if st.button("Clôturer le mois", type="primary", key="bourse_close"):
                s = bourse.load()
                ok, msg = bourse.close_month(s, username, quota, reading, month)
                bourse.save(s)
                st.session_state["bourse_msg"] = (ok, msg)
                st.rerun()

    st.markdown(f"**Offres disponibles à {acc['province']}**")
    others = [o for o in state["offers"] if o["province"] == acc["province"] and o["seller"] != username]
    if not others:
        st.caption("Aucune offre disponible pour le moment.")
    else:
        h = st.columns([2, 1, 1, 1.4, 1])
        for col, label in zip(h, ["Vendeur", "Quantité", "Prix", "À acheter", ""]):
            col.caption(label)
        for o in others:
            c = st.columns([2, 1, 1, 1.4, 1])
            c[0].write(state["accounts"][o["seller"]]["name"])
            c[1].write(f"{o['qty']} tokens")
            c[2].write(f"{o['price']:.2f} MAD")
            qty = c[3].number_input("Quantité", min_value=1, max_value=int(o["qty"]),
                                    value=min(50, int(o["qty"])), key=f"buy_qty_{o['id']}",
                                    label_visibility="collapsed")
            if c[4].button("Acheter", key=f"buy_{o['id']}"):
                s = bourse.load()
                ok, msg = bourse.buy(s, username, o["id"], qty)
                if ok:
                    bourse.save(s)
                st.session_state["bourse_msg"] = (ok, msg)
                st.rerun()

    st.markdown("**Vendre mes tokens**")
    if acc["balance"] < 1:
        st.caption("Vous n'avez aucun token disponible : économisez au moins 20 % de votre quota pour en gagner.")
    else:
        v1, v2, v3 = st.columns([1, 1, 1])
        sell_qty = v1.number_input("Quantité", min_value=1, max_value=int(acc["balance"]),
                                   value=min(100, int(acc["balance"])), step=10, key="sell_qty")
        sell_price = v2.number_input("Prix (MAD par token)", min_value=0.1, max_value=float(rules["prix_plafond"]),
                                     value=float(min(rules["prix_ref"], rules["prix_plafond"])),
                                     step=0.1, key="sell_price")
        v3.write("")
        v3.write("")
        if v3.button("Publier l'offre", key="sell_publish"):
            s = bourse.load()
            ok, msg = bourse.create_offer(s, username, sell_qty, sell_price)
            if ok:
                bourse.save(s)
            st.session_state["bourse_msg"] = (ok, msg)
            st.rerun()

    mine = [o for o in state["offers"] if o["seller"] == username]
    if mine:
        st.markdown("**Mes offres en cours**")
        for o in mine:
            c = st.columns([3, 1])
            c[0].write(f"{o['qty']} tokens à {o['price']:.2f} MAD")
            if c[1].button("Annuler", key=f"cancel_{o['id']}"):
                s = bourse.load()
                ok, msg = bourse.cancel_offer(s, o["id"], username)
                if ok:
                    bourse.save(s)
                st.session_state["bourse_msg"] = (ok, msg)
                st.rerun()

    rows = []
    for t in state["transactions"]:
        if username not in (t["seller"], t["buyer"]):
            continue
        if t["type"] == "credit":
            kind, other = "Crédit d'économie", ""
        elif t["seller"] == username:
            kind, other = "Vente", state["accounts"][t["buyer"]]["name"]
        else:
            kind, other = "Achat", state["accounts"][t["seller"]]["name"]
        rows.append({"Date": t["time"].replace("T", " "), "Opération": kind, "Tokens": t["qty"],
                     "Prix (MAD)": t["price"], "Contrepartie": other, "Détail": t.get("note", "")})
    if rows:
        st.markdown("**Historique**")
        st.dataframe(pd.DataFrame(rows).iloc[::-1], use_container_width=True, hide_index=True)


def summary(f):
    lat, lon = farm_coords(f)
    hero(
        "Dashboard agricole",
        f"{user['name']} · {f['province']}",
        [f["crop"], f"{f['area_ha']} ha", f["irrigation"], f"Eau : {f['ec_water']} dS/m"],
    )

    with st.expander("Position de l'exploitation", expanded=False):
        if "lat" not in f:
            st.caption("Position par défaut (centre de la province). Modifiez la configuration pour placer votre parcelle.")
        else:
            st.caption(f"Latitude {lat:.5f} · Longitude {lon:.5f}")
        st_folium(make_map(lat, lon, 13), height=280, use_container_width=True, returned_objects=[], key="summary_map")

    if st.button("Modifier la configuration"):
        st.session_state["editing"] = True
        st.rerun()
    modules = dict(zip(FARM_NAV, [irrigation_section, evapo_section, nexus_section,
                                  salinity_section, bourse_section, weather_section]))
    choice = st.session_state.get("farm_nav", FARM_NAV[0])
    modules[choice](f)


if st.session_state["editing"]:
    hero("Bienvenue sur AquaPilot", "Décrivez votre exploitation pour recevoir des recommandations adaptées.")
    config_form(farm)
else:
    summary(farm)
