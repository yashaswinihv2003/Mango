# ============================================================
# 🥭 FARMER’S MANGO PROFIT NAVIGATOR – FINAL CLOUD VERSION 🥭
# ============================================================

import streamlit as st
import pandas as pd
import numpy as np
import folium
import requests
import plotly.express as px
from streamlit.components.v1 import html

st.set_page_config(layout="wide")

st.title("🥭 Farmer’s Mango Profit Navigator 🥭")
st.subheader("🧭 Find the Best Market. Earn the Highest Return.")

# ---------------- LOAD DATA ----------------
@st.cache_data
def load_data():
    villages = pd.read_csv("Village data.csv")
    prices = pd.read_csv("cleaned_price_data.csv")
    geo = pd.read_csv("cleaned_mandi_location.csv")
    processing = pd.read_csv("cleaned_processing_facilities.csv")
    pulp = pd.read_csv("Pulp_units_merged_lat_long.csv")
    pickle_units = pd.read_csv("cleaned_pickle_units.csv")
    local_export = pd.read_csv("cleaned_local_export.csv")
    abroad_export = pd.read_csv("cleaned_abroad_export.csv")

    for df in [villages, prices, geo, processing,
               pulp, pickle_units, local_export, abroad_export]:
        df.columns = df.columns.str.strip().str.lower()

    return villages, prices, geo, processing, pulp, pickle_units, local_export, abroad_export

villages, prices, geo, processing, pulp, pickle_units, local_export, abroad_export = load_data()

# ---------------- HELPERS ----------------
def detect_lat_lon(df):
    lat, lon = None, None
    for c in df.columns:
        if "lat" in c:
            lat = c
        if "lon" in c:
            lon = c
    return lat, lon

def detect_name(df):
    for col in df.columns:
        if any(x in col for x in ["name", "market", "unit", "company", "place", "village"]):
            return col
    return df.columns[0]

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    lat1, lon1, lat2, lon2 = map(np.radians,[lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2)**2
    return R * 2*np.arcsin(np.sqrt(a))

def get_road_route(lat1, lon1, lat2, lon2):
    url = f"https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        if "routes" in data:
            coords = data["routes"][0]["geometry"]["coordinates"]
            return [(c[1], c[0]) for c in coords]
    except:
        return None
    return None

# ---------------- SIDEBAR ----------------
st.sidebar.header("👨‍🌾 Farmer Details")

farmer_name = st.sidebar.text_input("Farmer Name")

village_name_col = detect_name(villages)

selected_village = st.sidebar.selectbox(
    "Select Village",
    villages[village_name_col].unique()
)

variety = st.sidebar.selectbox(
    "Select Variety",
    ["Banganapalli","Totapuri","Neelam","Rasalu"]
)

quantity_qtl = st.sidebar.number_input("Quantity (Quintals)", min_value=1, value=10)

run = st.sidebar.button("🚀 Run Smart Analysis")

# ---------------- VARIETY RULES ----------------
variety_acceptance = {
    "Mandi":["Banganapalli","Totapuri","Neelam","Rasalu"],
    "Processing":["Totapuri","Neelam"],
    "Pulp":["Totapuri"],
    "Pickle":["Totapuri","Rasalu"],
    "Local Export":["Banganapalli"],
    "Abroad Export":["Banganapalli"]
}

margin_map = {
    "Mandi":0,
    "Processing":0.03,
    "Pulp":0.04,
    "Pickle":0.025,
    "Local Export":0.05,
    "Abroad Export":0.07
}

# ---------------- MAIN ----------------
if run:

    st.markdown(f"## 🙏 Namaste **{farmer_name}**")

    village_row = villages[villages[village_name_col]==selected_village].iloc[0]
    lat_col, lon_col = detect_lat_lon(villages)

    v_lat = village_row[lat_col]
    v_lon = village_row[lon_col]

    mandi_data = prices.merge(geo, on="market", how="left")
    lat_m, lon_m = detect_lat_lon(mandi_data)
    mandi_data = mandi_data.dropna(subset=[lat_m,lon_m])

    mandi_data["distance"] = mandi_data.apply(
        lambda r: haversine(v_lat,v_lon,r[lat_m],r[lon_m]),axis=1)

    nearest = mandi_data.loc[mandi_data["distance"].idxmin()]
    base_price = nearest["today_price(rs/kg)"]

    results = []

    category_dfs = {
        "Mandi":mandi_data,
        "Processing":processing,
        "Pulp":pulp,
        "Pickle":pickle_units,
        "Local Export":local_export,
        "Abroad Export":abroad_export
    }

    for cat,df in category_dfs.items():

        if variety not in variety_acceptance[cat]:
            continue

        lat,lon = detect_lat_lon(df)
        name_col = detect_name(df)

        for _,row in df.iterrows():

            if pd.notnull(row[lat]) and pd.notnull(row[lon]):

                dist = haversine(v_lat,v_lon,row[lat],row[lon])
                transport = dist * 12 * quantity_qtl
                revenue = base_price*(1+margin_map[cat])*100*quantity_qtl
                net = revenue - transport

                results.append({
                    "Category":cat,
                    "Name":row[name_col],
                    "Distance_km":round(dist,2),
                    "Net Profit":round(net,2),
                    "Lat":row[lat],
                    "Lon":row[lon]
                })

    df_top = pd.DataFrame(results).drop_duplicates(
        subset=["Name","Category"]
    ).sort_values("Net Profit",ascending=False).head(10).reset_index(drop=True)

    df_top["Rank"] = df_top.index + 1

    st.subheader("📊 Profit Comparison")
    fig = px.bar(df_top, x="Name", y="Net Profit", color="Category")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("🗺 Top 10 Routes")

    # ---------------- MAP ----------------
    m = folium.Map(location=[v_lat,v_lon],zoom_start=9)

    # Village Home Icon
    folium.Marker(
        [v_lat,v_lon],
        popup="🏡 Village",
        icon=folium.Icon(color="black", icon="home", prefix="fa")
    ).add_to(m)

    for _,row in df_top.iterrows():

        route = get_road_route(v_lat,v_lon,row["Lat"],row["Lon"])

        # Most profitable = star + dark red route
        if row["Rank"] == 1:
            icon_color = "red"
            route_color = "darkred"
            route_weight = 7
            icon_symbol = "star"
        else:
            icon_color = "green"
            route_color = "orange"
            route_weight = 4
            icon_symbol = "info-sign"

        # Marker with distance
        folium.Marker(
            [row["Lat"],row["Lon"]],
            popup=f"{row['Name']}<br>Distance: {row['Distance_km']} km",
            icon=folium.Icon(color=icon_color, icon=icon_symbol)
        ).add_to(m)

        if route:
            folium.PolyLine(
                route,
                color=route_color,
                weight=route_weight
            ).add_to(m)

    html(m._repr_html_(), height=650)
