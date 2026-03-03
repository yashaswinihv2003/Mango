# ============================================================
# 🥭 FARMER’S MANGO PROFIT NAVIGATOR – PROFESSIONAL MERGED VERSION
# Combines User UI + Strong Routing + Highlighted Best Route
# ============================================================

import streamlit as st
import pandas as pd
import numpy as np
import folium
import requests
import plotly.express as px
from streamlit_folium import st_folium

st.set_page_config(layout="wide")
st.title("🥭 Farmer’s Mango Profit Navigator 🥭")
st.subheader("🧭 Find the Best Market. Earn the Highest Return.")

# ================= CONFIG =================
RADIUS_KM = 80
TRANSPORT_RATE_PER_KM_PER_QTL = 12

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

# ================= HELPERS =================
def detect_lat_lon(df):
    lat, lon = None, None
    for c in df.columns:
        if "lat" in c: lat = c
        if "lon" in c: lon = c
    return lat, lon

def detect_name(df):
    for col in ["market","unit_name","company_name","name","place"]:
        if col in df.columns:
            return col
    return df.columns[0]

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
        url = f"https://router.project-osrm.org/route/v1/driving/{v_lon},{v_lat};{d_lon},{d_lat}?overview=full&geometries=geojson"
        response = requests.get(url, timeout=10)
        data = response.json()

        if "routes" not in data:
            return None, None

        distance_km = data["routes"][0]["distance"] / 1000
        coords = data["routes"][0]["geometry"]["coordinates"]
        latlon = [(c[1], c[0]) for c in coords]

        return distance_km, latlon
    except:
        return None, None

# ================= SIDEBAR =================
st.sidebar.header("👨‍🌾 Farmer Details")

farmer_name = st.sidebar.text_input("Farmer Name 🥭")

selected_village = st.sidebar.selectbox(
    "Select Village 🏡",
    villages[detect_name(villages)].unique()
)

variety = st.sidebar.selectbox(
    "Select Variety 🥭",
    ["Banganapalli","Totapuri","Neelam","Rasalu"]
)

quantity_qtl = st.sidebar.number_input("Quantity (Quintals) 📦", min_value=1, value=10)

if "run" not in st.session_state:
    st.session_state.run = False

if st.sidebar.button("🚀 Run Smart Analysis"):
    st.session_state.run = True

# ================= VARIETY RULES =================
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

# ================= MAIN =================
if st.session_state.run:

    st.markdown(f"## 🙏 Namaste **{farmer_name}** 🥭")

    village_row = villages[villages[detect_name(villages)]==selected_village].iloc[0]
    v_lat, v_lon = village_row[detect_lat_lon(villages)[0]], village_row[detect_lat_lon(villages)[1]]

    mandi_data = prices.merge(geo,on="market",how="left")
    lat_m, lon_m = detect_lat_lon(mandi_data)
    mandi_data = mandi_data.dropna(subset=[lat_m,lon_m])

    mandi_data["distance"] = mandi_data.apply(
        lambda r: haversine(v_lat,v_lon,r[lat_m],r[lon_m]),axis=1)

    nearest = mandi_data.loc[mandi_data["distance"].idxmin()]
    base_price = nearest["today_price(rs/kg)"]

    st.subheader("Nearest Market")
    st.write("Market:", nearest["market"])
    st.write("Base Price (₹/kg):", base_price)

    results=[]
    routes=[]

    category_dfs = {
        "Mandi":mandi_data,
        "Processing":processing,
        "Pulp":pulp,
        "Pickle":pickle_units,
        "Local Export":local_export,
        "Abroad Export":abroad_export
    }

    for cat,df in category_dfs.items():
        if variety not in variety_acceptance[cat]: continue
        lat,lon = detect_lat_lon(df)
        name_col = detect_name(df)
        if lat is None: continue

        df = df.drop_duplicates(subset=[name_col])

        for _,row in df.iterrows():

            km, route_coords = get_route(v_lat, v_lon, row[lat], row[lon])
            if km is None or km > RADIUS_KM:
                continue

            transport = km * TRANSPORT_RATE_PER_KM_PER_QTL * quantity_qtl
            revenue = base_price*(1+margin_map[cat])*100*quantity_qtl
            net = revenue - transport

            results.append({
                "Category":cat,
                "Name":row[name_col],
                "Distance_km":round(km,2),
                "Net Profit":round(net,2),
                "Lat":row[lat],
                "Lon":row[lon]
            })

            routes.append({
                "Name":row[name_col],
                "coords":route_coords
            })

    df_top = pd.DataFrame(results).drop_duplicates(
        subset=["Name","Category"]
    ).sort_values("Net Profit",ascending=False).head(10).reset_index(drop=True)

    df_top["Rank"]=df_top.index+1

    st.subheader("Top 10 Alternatives")
    st.dataframe(df_top)

    # ================= BAR CHART =================
    fig = px.bar(df_top, x="Name", y="Net Profit",
                 title="Profit Comparison",
                 color="Net Profit")
    st.plotly_chart(fig, use_container_width=True)

    # ================= MAP =================
    st.subheader("🗺 Top 10 Alternatives with Road Routes")

    m = folium.Map(location=[v_lat,v_lon],zoom_start=9)

    folium.Marker([v_lat,v_lon],
                  popup="Village",
                  icon=folium.Icon(color="black")).add_to(m)

    for _,row in df_top.iterrows():

        road_path = next((r["coords"] for r in routes if r["Name"]==row["Name"]), None)

        if row["Rank"]==1:
            color="darkred"
            weight=7
            icon=folium.Icon(color="red",icon="star")
        else:
            color="orange"
            weight=4
            icon=folium.Icon(color="green")

        if road_path:
            folium.PolyLine(road_path,color=color,weight=weight).add_to(m)

        folium.Marker([row["Lat"],row["Lon"]],
                      popup=f"{row['Name']} | Rank {row['Rank']}",
                      icon=icon).add_to(m)

    st_folium(m,width=1100,height=600)
