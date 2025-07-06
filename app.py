# ===============================
# Import required libraries
# ===============================
# import folium.map
import streamlit as st  # For building the web app interface
import pandas as pd  # For working with tabular data
import folium  # For creating interactive maps
from streamlit_folium import st_folium  # For displaying folium maps inside Streamlit
import geopandas as gpd  # For working with geospatial data (shapefiles, etc.)
from geodatasets import get_path  # for borough shapes
import plotly.express as px
from folium.plugins import MarkerCluster
import time


# ===============================
# App configuration
# ===============================
st.set_page_config(page_title="NYC WiFi Hotspots", layout="wide")

# ===============================
# HTML CSS embeded in app using markdown() to make static header
# ===============================
st.markdown(
    """
    <style>
    .fixed-title {
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        background: white;
        z-index: 1000;
        padding-top: 1rem;
        padding-bottom: 1rem;
        border-bottom: 1px solid #eee;
        text-align: center;
        color: black;
    }
    @media (prefers-color-scheme: dark) {
        .fixed-title {
            background: black !important;
            color: white !important;
            border-bottom: 1px solid #444;
        }
    }
    .block-container {
        padding-top: 7rem !important;
    }
    </style>
    <div class="fixed-title">
        <h1>📶 NYC WiFi Hotspots</h1>
    </div>
    """,
    unsafe_allow_html=True,
)


# ===============================
# Variable Definitions / Comments
# ===============================
# df: The main DataFrame containing all Wi-Fi hotspot data loaded from the CSV.
# columns_to_show: List of original column names from df to display in the table and use for searching.
# column_rename_map: Dictionary mapping original column names (keys) to user-friendly display names (values).
# search: The user's search query input (string).
# search_columns: List of user-friendly column names (plus "All") for the search dropdown.
# selected_column_display: The user-friendly column name selected in the dropdown.
# selected_column: The original column name (from df) corresponding to selected_column_display, or "All".
# mask: Boolean Series used to filter df based on the search query.
# filtered_df: The DataFrame after filtering according to the search query and selected column.
# display_df: The filtered DataFrame, but with columns renamed for display.
# borough_counts: DataFrame with counts of hotspots per borough code.
# borough_code_to_name: Dictionary mapping borough codes (1-5) to borough names.
# borough_summary: DataFrame summarizing borough code, borough name, and number of hotspots.
# fig: Plotly figure object for the bar chart of hotspot counts by borough.


# ===============================
# Load the dataset
# ===============================
df = pd.read_csv(
    "NYC_Wi-Fi_Hotspot_Locations_20250703.csv"
)  # Make sure the file is in the same folder as app.py

# Get a list of column headings
print(df.columns.tolist())

# ===============================
# Clean and prepare data
# ===============================
# Drop rows missing coordinates
df = df.dropna(subset=["Latitude", "Longitude"])

# Convert lat/lon to numeric (safety)
df["Latitude"] = pd.to_numeric(df["Latitude"], errors="coerce")
df["Longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")

st.subheader("Find Your Wi-Fi Hotspot in NYC")

# Choose columns to display
columns_to_show = [
    "Provider",
    "Name",
    "Location",
    "Location_T",
    "SSID",
    "Borough Name",
    "Neighborhood Tabulation Area (NTA)",
    "Postcode",
    "Location (Lat, Long)",
]

# Create a mapping from old column names to new, user-friendly names
column_rename_map = {
    "Provider": "Provider",
    "Name": "Hotspot Name",
    "Location": "Address/Location",
    "Location_T": "Location Type",
    "SSID": "WiFi Network (SSID)",
    "Borough Name": "Borough",
    "Neighborhood Tabulation Area (NTA)": "Neighborhood",
    "Postcode": "Postcode",
    "Location (Lat, Long)": "Coordinates",
}

# Set the default to the table arranging rows in ascending order of postal codes
df = df.sort_values("Postcode", ascending=True)


# Drop down menu
search_columns = ["All"] + list(column_rename_map.values())

col1, col2, col3, col4 = st.columns([5, 3, 1, 6])
with col2:
    selected_column_display = st.selectbox("Filter by:", search_columns)

# Map display name back to original column name for filtering
if selected_column_display == "All":
    selected_column = "All"
else:
    selected_column = {v: k for k, v in column_rename_map.items()}[
        selected_column_display
    ]

# Now set suggestions based on the selected column
if selected_column == "All":
    all_suggestions = pd.unique(
        pd.concat([df[col].astype(str) for col in columns_to_show])
    ).tolist()
else:
    all_suggestions = df[selected_column].dropna().astype(str).unique().tolist()


# Place this before the selectbox is rendered
if "clear_search" not in st.session_state:
    st.session_state.clear_search = False

with col1:
    cols1, cols2 = st.columns([8, 1])

    with cols2:
        if st.button("🗑️", key="clear_button", help="Clear Search"):
            st.session_state["search_key"] = ""
            st.session_state.clear_search = True
            st.rerun()

    with cols1:
        search = st.selectbox(
            "Search for a hotspot, borough, postcode, etc.",
            options=[""] + all_suggestions,
            index=0,
            key="search_key",
        )


# Filter the DataFrame based on the search query and selected column
if search:
    if selected_column == "All":
        mask = df[columns_to_show].apply(
            lambda row: row.astype(str).str.contains(search, case=False).any(), axis=1
        )
        filtered_df = df[mask]
    else:
        mask = df[selected_column].astype(str).str.contains(search, case=False)
        filtered_df = df[mask]
else:
    filtered_df = df


# Apply renaming only to the columns you want to show
display_df = filtered_df[columns_to_show].rename(columns=column_rename_map)

table_col, no_col, map_col = st.columns([8, 1, 6])

with table_col:
    selected_row = st.data_editor(
        display_df,
        use_container_width=True,
        height=400,
        disabled=True,
        hide_index=True,
        key="hotspot_table",
    )


st.markdown(
    """
    <style>
    /* Force the folium map iframe to a fixed height and remove extra space */
    iframe[title="streamlit_folium.st_folium"] {
        height: 400px !important;
        min-height: 400px !important;
        max-height: 400px !important;
        margin-bottom: 0 !important;
        padding-bottom: 0 !important;
        display: block;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

with col4:
    if st.button("🔄 Refresh 200 Random Hotspots", key="refresh_button"):
        st.session_state.hotspot_sample = df.sample(n=200)
        st.session_state.refresh_clicked = True


with map_col:

    # Create the base map centered on NYC
    m = folium.Map(location=[40.7128, -74.0060], zoom_start=11)

    # Decide what data to show: filtered search or random sample
    if search:
        map_data = filtered_df
    else:
        if "hotspot_sample" not in st.session_state:
            st.session_state.hotspot_sample = df.sample(n=200, random_state=42)
        map_data = st.session_state.hotspot_sample

    # Create a FeatureGroup to hold all the markers
    hotspot_group = folium.FeatureGroup(name="Hotspots")

    # Get selected row from table (via session state)
    selected_row = st.session_state.get("hotspot_table", {})

    # Loop over whichever data we're displaying on the map
    for _, row in map_data.iterrows():
        # Default marker color
        color = "blue"

        # Highlight selected row in green
        if selected_row and (
            row["Location"] == selected_row.get("Address/Location")
            and row["SSID"] == selected_row.get("WiFi Network (SSID)")
        ):
            color = "green"

        # Create and add the marker
        marker = folium.Marker(
            location=[row["Latitude"], row["Longitude"]],
            popup=row.get("Name", ""),
            tooltip=row.get("SSID", ""),
            icon=folium.Icon(icon="map-marker", prefix="fa", color=color),
        )
        hotspot_group.add_child(marker)

    # Add markers to the map
    m.add_child(hotspot_group)

    # Display the map once
    st_folium(m, use_container_width=True, height=400)


# ===============================
# Table showing boroughs and number of hotspots
# ===============================
# Count how many times each borough code appears
borough_counts = df["BoroCode"].value_counts().reset_index()
borough_counts.columns = ["Borough Code", "Number of Hotspots"]

# Map borough codes to names
borough_code_to_name = {
    1: "Manhattan",
    2: "Bronx",
    3: "Brooklyn",
    4: "Queens",
    5: "Staten Island",
}
borough_counts["Borough Name"] = borough_counts["Borough Code"].map(
    borough_code_to_name
)

# Reorder columns: Borough Code, Borough Name, Number of Hotspots
borough_summary = borough_counts[["Borough Code", "Borough Name", "Number of Hotspots"]]

# Show the new DataFrame
st.subheader("Hotspot Count by Borough")

# bar chart using plotly
fig = px.bar(
    borough_summary,
    x="Borough Name",
    y="Number of Hotspots",
    labels={"Borough Name": "Borough", "Number of Hotspots": "Hotspot Count"},
    text="Number of Hotspots",
)
fig.update_layout(xaxis_tickangle=0)  # 0 means horizontal labels

st.plotly_chart(fig, use_container_width=True)


# Footer
st.markdown(
    """
    <hr>
    <p style="text-align:center; color: gray; font-size: smaller;">
        Streamlit App made by **Varun SA · MS CDP 2025‑26 · Columbia University** Version 1.1
    </p>
    """,
    unsafe_allow_html=True,
)
