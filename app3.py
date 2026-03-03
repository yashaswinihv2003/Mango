# ============================================================
# PROFESSIONAL FARMER DECISION SUPPORT SYSTEM
# FINAL PROFESSIONAL VERSION (Highlighted Routes + No Duplicates)
# ============================================================

import streamlit as st
import pandas as pd
import numpy as np
import requests
import folium
import plotly.express as px
from streamlit.components.v1 import html

st.set_page_config(page_title="Farmer DSS", layout="wide")
st.title("🍋 Professional Farmer Decision Support System")

# ================= CONFIG =================
RADIUS_KM = 80
TRANSPORT_RATE_PER_10KM_PER_TONNE = 2000
SPOILAGE_PER_10KM = 0.004
HANDLING_RISK = 0.002

# ================= LOAD DATA =================
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

# ================= HELPER FUNCTIONS =================
def detect_cols(df):
    name, lat, lon = None, None, None
    for c in df.columns:
        if "lat" in c:
            lat = c
        if "lon" in c:
            lon = c
        if any(x in c for x in ["name","firm","facility","hub","market","place","panchayat","village"]):
            name = c
    return name, lat, lon


def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    lat1, lon1, lat2, lon2 = map(np.radians,[lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2)**2
    return R * 2*np.arcsin(np.sqrt(a))


@st.cache_data(show_spinner=False)
def get_route(v_lat, v_lon, d_lat, d_lon):
    try:
        url = (
            f"https://router.project-osrm.org/route/v1/driving/"
            f"{v_lon},{v_lat};{d_lon},{d_lat}?"
            f"overview=full&geometries=geojson"
        )
        response = requests.get(url, timeout=10)
        data = response.json()

        if response.status_code != 200 or "routes" not in data:
            return None, None

        distance_km = data["routes"][0]["distance"] / 1000
        coords = data["routes"][0]["geometry"]["coordinates"]
        latlon = [(c[1], c[0]) for c in coords]

        return distance_km, latlon
    except:
        return None, None


# ================= SIDEBAR =================
st.sidebar.header("Farmer Input Panel")

village_input = st.sidebar.text_input("Enter Village Name")
variety = st.sidebar.selectbox(
    "Select Mango Variety",
    ["Banganapalli","Totapuri","Neelam","Rasalu"]
)

TONNES = st.sidebar.number_input(
    "Enter Quantity (Tonnes)",
    min_value=1,
    max_value=100,
    value=10
)

run = st.sidebar.button("Run Smart Analysis")

# ================= VARIETY LOGIC =================
variety_acceptance = {
    "Mandi": ["Banganapalli","Totapuri","Neelam","Rasalu"],
    "Processing": ["Totapuri","Neelam"],
    "Pulp": ["Totapuri"],
    "Pickle": ["Totapuri","Rasalu"],
    "Local Export": ["Banganapalli"],
    "Abroad Export": ["Banganapalli"]
}

category_params = {
    "Mandi": {"margin":0},
    "Processing": {"margin":0.03},
    "Pulp": {"margin":0.04},
    "Pickle": {"margin":0.025},
    "Local Export": {"margin":0.05},
    "Abroad Export": {"margin":0.07},
}

# ================= RUN =================
if run:

    v_name_col, v_lat_col, v_lon_col = detect_cols(villages)
    villages[v_name_col] = villages[v_name_col].str.lower()

    if village_input.lower() not in villages[v_name_col].values:
        st.error("Village not found")
        st.stop()

    village = villages[villages[v_name_col] == village_input.lower()].iloc[0]
    v_lat = village[v_lat_col]
    v_lon = village[v_lon_col]

    # BASE PRICE
    mandi_data = prices.merge(geo, on="market", how="left")
    mandi_data = mandi_data.dropna(subset=["latitude","longitude"])

    mandi_data["approx"] = mandi_data.apply(
        lambda r: haversine(v_lat,v_lon,r["latitude"],r["longitude"]), axis=1
    )

    nearest = mandi_data.loc[mandi_data["approx"].idxmin()]
    base_price = nearest["today_price(rs/kg)"]

    st.subheader("Nearest Market")
    st.write("Market:", nearest["market"])
    st.write("Base Price (₹/kg):", base_price)

    # COLLECT OPTIONS
    def collect_all(df, category):
        if variety not in variety_acceptance[category]:
            return pd.DataFrame()

        name_col, lat_col, lon_col = detect_cols(df)
        rows = []

        for _, row in df.iterrows():
            if pd.notnull(row[lat_col]) and pd.notnull(row[lon_col]):
                rows.append({
                    "Type":category,
                    "Name":row[name_col],
                    "Lat":row[lat_col],
                    "Lon":row[lon_col]
                })

        return pd.DataFrame(rows)

    df_all = pd.concat([
        collect_all(mandi_data,"Mandi"),
        collect_all(processing,"Processing"),
        collect_all(pulp,"Pulp"),
        collect_all(pickle_units,"Pickle"),
        collect_all(local_export,"Local Export"),
        collect_all(abroad_export,"Abroad Export")
    ], ignore_index=True)

    if df_all.empty:
        st.error("No facilities available")
        st.stop()

    # REMOVE DUPLICATES EARLY
    df_all = df_all.drop_duplicates(subset=["Type","Name"])

    # PRE-FILTER CLOSEST 15
    df_all["approx_km"] = df_all.apply(
        lambda r: haversine(v_lat, v_lon, r["Lat"], r["Lon"]),
        axis=1
    )
    df_all = df_all.sort_values("approx_km").head(15)

    results = []
    routes_data = []

    for _, row in df_all.iterrows():

        km, route_coords = get_route(v_lat, v_lon, row["Lat"], row["Lon"])

        if km is None or km > RADIUS_KM:
            continue

        cat = row["Type"]
        margin = category_params[cat]["margin"]

        adjusted_price = base_price * (1 + margin)
        revenue = adjusted_price * 1000 * TONNES
        transport = (km/10) * TRANSPORT_RATE_PER_10KM_PER_TONNE * TONNES

        spoilage_risk = SPOILAGE_PER_10KM * (km/10)
        risk_rate = spoilage_risk + HANDLING_RISK
        risk_cost = revenue * risk_rate

        net_profit = revenue - transport - risk_cost

        results.append({
            "Type":cat,
            "Name":row["Name"],
            "Distance_km":round(km,2),
            "Net_Profit":round(net_profit,2),
            "Lat":row["Lat"],
            "Lon":row["Lon"]
        })

        routes_data.append({
            "Name":row["Name"],
            "coords":route_coords
        })

    if not results:
        st.error("No road routes found")
        st.stop()

    df = pd.DataFrame(results).drop_duplicates(subset=["Type","Name"])
    df_top = df.sort_values("Distance_km")

    st.subheader("Top Options")
    st.dataframe(df_top)

    best = df_top.loc[df_top["Net_Profit"].idxmax()]
    st.success("🏆 Most Profitable Option")
    st.write(best)

    # PROFIT GRAPH
    fig = px.bar(df_top, x="Name", y="Net_Profit",
                 title="Profit Comparison")
    st.plotly_chart(fig, use_container_width=True)

    # ================= MAP =================
    m = folium.Map(location=[v_lat, v_lon], zoom_start=10)

    folium.Marker([v_lat, v_lon],
                  popup="Village",
                  icon=folium.Icon(color="green")).add_to(m)

    for route in routes_data:
        name = route["Name"]
        coords = route["coords"]

        if coords is None:
            continue

        if name == best["Name"]:
            color = "darkred"
            weight = 6
        else:
            color = "blue"
            weight = 3

        folium.PolyLine(
            coords,
            color=color,
            weight=weight,
            opacity=0.8
        ).add_to(m)

    for _, row in df_top.iterrows():
        folium.Marker(
            [row["Lat"], row["Lon"]],
            popup=f"{row['Name']} ({row['Type']})",
            icon=folium.Icon(color="red" if row["Name"]==best["Name"] else "blue")
        ).add_to(m)

    html(m._repr_html_(), height=600)
