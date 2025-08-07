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
import requests
import json
from streamlit_geolocation import streamlit_geolocation


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
    
    /* Style for location info */
    .location-info {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 5px;
        margin: 10px 0;
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


# ===============================
# Routing Functions
# ===============================
def get_directions_ors(start_lat, start_lon, end_lat, end_lon, api_key):
    """
    Get directions using OpenRouteService API
    Returns decoded coordinates for the route
    """
    try:
        # OpenRouteService API endpoint for directions
        url = "https://api.openrouteservice.org/v2/directions/foot-walking"

        headers = {
            "Accept": "application/json, application/geo+json, application/gpx+xml, img/png; charset=utf-8",
            "Authorization": api_key,
            "Content-Type": "application/json; charset=utf-8",
        }

        body = {
            "coordinates": [[start_lon, start_lat], [end_lon, end_lat]],
            "format": "geojson",
        }

        response = requests.post(url, json=body, headers=headers)

        if response.status_code == 200:
            data = response.json()
            if "features" in data and len(data["features"]) > 0:
                # Extract coordinates from the route
                coordinates = data["features"][0]["geometry"]["coordinates"]
                # Convert from [lon, lat] to [lat, lon] for folium
                route_coords = [[coord[1], coord[0]] for coord in coordinates]
                return route_coords
        else:
            st.error(f"Routing API error: {response.status_code}")
            return None

    except Exception as e:
        st.error(f"Error getting directions: {str(e)}")
        return None


def get_directions_osrm(start_lat, start_lon, end_lat, end_lon):
    """
    Get directions using free OSRM API (no API key required)
    Returns decoded coordinates for the route
    """
    try:
        # OSRM API endpoint for walking directions
        url = f"http://router.project-osrm.org/route/v1/foot/{start_lon},{start_lat};{end_lon},{end_lat}"

        params = {"overview": "full", "geometries": "geojson"}

        response = requests.get(url, params=params)

        if response.status_code == 200:
            data = response.json()
            if "routes" in data and len(data["routes"]) > 0:
                # Extract coordinates from the route
                coordinates = data["routes"][0]["geometry"]["coordinates"]
                # Convert from [lon, lat] to [lat, lon] for folium
                route_coords = [[coord[1], coord[0]] for coord in coordinates]
                return (
                    route_coords,
                    data["routes"][0].get("duration", 0),
                    data["routes"][0].get("distance", 0),
                )
        else:
            st.error(f"Routing API error: {response.status_code}")
            return None, None, None

    except Exception as e:
        st.error(f"Error getting directions: {str(e)}")
        return None, None, None


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
            # Clear any selected hotspot from map clicks
            if "selected_hotspot" in st.session_state:
                del st.session_state.selected_hotspot
            # Clear directions when clearing search
            if "show_directions" in st.session_state:
                del st.session_state.show_directions
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
elif "selected_hotspot" in st.session_state:
    # Show only the selected hotspot from map click
    selected_hotspot = st.session_state.selected_hotspot
    filtered_df = df[
        (df["Latitude"] == selected_hotspot["lat"])
        & (df["Longitude"] == selected_hotspot["lon"])
    ]
else:
    filtered_df = df


# Apply renaming only to the columns you want to show
display_df = filtered_df[columns_to_show].rename(columns=column_rename_map)

# Normal mode - show table and map side by side
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
    # Create three columns for the buttons
    btn_col1, btn_col2, btn_col3 = st.columns(3)

    with btn_col1:
        if st.button("🔄 Refresh 200 Random Hotspots", key="refresh_button"):
            st.session_state.hotspot_sample = df.sample(n=200)
            st.session_state.refresh_clicked = True
            # Clear any selected hotspot to return to initial state
            if "selected_hotspot" in st.session_state:
                del st.session_state.selected_hotspot
            # Clear directions when refreshing
            if "show_directions" in st.session_state:
                del st.session_state.show_directions
            st.rerun()

    with btn_col2:
        # Initialize location sharing state if it doesn't exist
        if "location_shared" not in st.session_state:
            st.session_state.location_shared = False

        # Determine button type and text based on current state
        if st.session_state.location_shared:
            button_type = "primary"
            button_text = "📍 Location Shared"
        else:
            button_type = "secondary"
            button_text = "📍 Share Current Location"

        # When button is clicked, toggle the state
        if st.button(button_text, key="location_button", type=button_type):
            st.session_state.location_shared = not st.session_state.location_shared

            # If turning OFF location sharing, reset all location-related session state
            if not st.session_state.location_shared:
                # Clear all location data and flags
                if "user_location" in st.session_state:
                    del st.session_state.user_location
                if "location_requested" in st.session_state:
                    del st.session_state.location_requested
                # Clear directions when turning off location
                if "show_directions" in st.session_state:
                    del st.session_state.show_directions

            st.rerun()  # Force immediate rerun to update button appearance

    with btn_col3:
        # Initialize directions state
        if "show_directions" not in st.session_state:
            st.session_state.show_directions = False

        # Only show directions button if both location and hotspot are available
        can_show_directions = (
            st.session_state.location_shared
            and "user_location" in st.session_state
            and "selected_hotspot" in st.session_state
        )

        if can_show_directions:
            # Determine button type and text based on current state
            if st.session_state.show_directions:
                button_type = "primary"
                button_text = "🗺️ Directions On"
            else:
                button_type = "secondary"
                button_text = "🗺️ Get Directions"

            if st.button(button_text, key="directions_button", type=button_type):
                st.session_state.show_directions = not st.session_state.show_directions
                st.rerun()
        else:
            # Show disabled button with help text
            st.button(
                "🗺️ Get Directions",
                key="directions_disabled",
                disabled=True,
                help="Select a hotspot and share your location first",
            )


with map_col:
    # Create the base map centered on NYC (or user location if available)
    if st.session_state.location_shared and "user_location" in st.session_state:
        # Center map on user location if available
        center_lat = st.session_state.user_location["lat"]
        center_lon = st.session_state.user_location["lon"]
        zoom_level = 14  # Closer zoom when showing user location
    else:
        # Default NYC center
        center_lat = 40.7128
        center_lon = -74.0060
        zoom_level = 11

    m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom_level)

    # Add user location marker if location is shared
    if st.session_state.location_shared:
        if "user_location" not in st.session_state:
            st.info("📍 Location sharing is enabled. Choose an option below:")

            # Auto-detect location button
            col_detect, col_status = st.columns([3, 5])

            with col_detect:
                if st.button("🎯 Auto-Detect My Location", key="auto_detect"):
                    st.session_state.location_requested = True

            # Show location component when requested
            if st.session_state.get("location_requested", False):
                with col_status:
                    st.info(
                        "🔄 Getting your location... Please allow location access when prompted."
                    )

                # Call geolocation component
                location = streamlit_geolocation()

                # Check if we got valid coordinates
                if location:
                    lat = location.get("latitude")
                    lon = location.get("longitude")

                    if lat is not None and lon is not None and lat != 0 and lon != 0:
                        st.session_state.user_location = {"lat": lat, "lon": lon}
                        st.session_state.location_requested = False  # Reset flag
                        st.success(f"✅ Location detected: {lat:.4f}, {lon:.4f}")
                        st.rerun()
                    else:
                        # Still waiting for location or got null values
                        st.write("⏳ Waiting for location permissions...")
                else:
                    st.write("⏳ Initializing location detector...")

            # Manual entry fallback
            st.markdown("**Or enter coordinates manually:**")
            col_lat, col_lon, col_btn = st.columns([3, 3, 2])
            with col_lat:
                user_lat = st.number_input(
                    "Your Latitude", value=40.7128, format="%.6f", key="user_lat"
                )
            with col_lon:
                user_lon = st.number_input(
                    "Your Longitude", value=-74.0060, format="%.6f", key="user_lon"
                )
            with col_btn:
                if st.button("📍 Set Location", key="set_location"):
                    st.session_state.user_location = {"lat": user_lat, "lon": user_lon}
                    st.success("Location set manually!")
                    st.rerun()

        # If user location is available, add it to the map
        if "user_location" in st.session_state:
            user_lat = st.session_state.user_location["lat"]
            user_lon = st.session_state.user_location["lon"]

            # Add user location marker (red marker)
            folium.Marker(
                location=[user_lat, user_lon],
                popup="📍 Your Location",
                tooltip="You are here",
                icon=folium.Icon(icon="user", prefix="fa", color="red"),
            ).add_to(m)

    # Decide what data to show: selected hotspot, filtered search, or random sample
    if "selected_hotspot" in st.session_state:
        # Show only the selected hotspot
        selected_hotspot = st.session_state.selected_hotspot
        map_data = df[
            (df["Latitude"] == selected_hotspot["lat"])
            & (df["Longitude"] == selected_hotspot["lon"])
        ]
    elif search:
        map_data = filtered_df
    else:
        if "hotspot_sample" not in st.session_state:
            st.session_state.hotspot_sample = df.sample(n=200, random_state=42)
        map_data = st.session_state.hotspot_sample

    # Create a FeatureGroup to hold all the WiFi markers
    hotspot_group = folium.FeatureGroup(name="Hotspots")

    # Get selected row from table (via session state)
    selected_row = st.session_state.get("hotspot_table", {})

    # Loop over whichever data we're displaying on the map
    for _, row in map_data.iterrows():
        # Default marker color
        color = "blue"

        # Highlight selected hotspot from map click in red
        if "selected_hotspot" in st.session_state:
            selected_hotspot = st.session_state.selected_hotspot
            if (
                row["Latitude"] == selected_hotspot["lat"]
                and row["Longitude"] == selected_hotspot["lon"]
            ):
                color = "red"

        # Highlight selected row from table in green (if different from map selection)
        elif selected_row and (
            row["Location"] == selected_row.get("Address/Location")
            and row["SSID"] == selected_row.get("WiFi Network (SSID)")
        ):
            color = "green"

        # Create and add the marker
        marker = folium.Marker(
            location=[row["Latitude"], row["Longitude"]],
            popup=f"<b>{row.get('Name', 'Unknown')}</b><br>SSID: {row.get('SSID', 'Unknown')}<br>Click marker to show only this hotspot",
            tooltip=row.get("SSID", ""),
            icon=folium.Icon(icon="wifi", prefix="fa", color=color),
        )
        hotspot_group.add_child(marker)

    # Add markers to the map
    m.add_child(hotspot_group)

    # Add directions if enabled and both locations are available
    if (
        st.session_state.get("show_directions", False)
        and "user_location" in st.session_state
        and "selected_hotspot" in st.session_state
    ):

        user_lat = st.session_state.user_location["lat"]
        user_lon = st.session_state.user_location["lon"]
        hotspot_lat = st.session_state.selected_hotspot["lat"]
        hotspot_lon = st.session_state.selected_hotspot["lon"]

        with st.spinner("🗺️ Getting directions..."):
            route_coords, duration, distance = get_directions_osrm(
                user_lat, user_lon, hotspot_lat, hotspot_lon
            )

            if route_coords:
                # Add the route to the map
                folium.PolyLine(
                    locations=route_coords,
                    color="blue",
                    weight=4,
                    opacity=0.8,
                    popup="Walking Route",
                ).add_to(m)

                # Show route info
                if duration and distance:
                    duration_min = int(duration / 60)
                    distance_km = round(distance / 1000, 2)
                    st.info(
                        f"🚶‍♂️ Walking time: ~{duration_min} minutes | Distance: {distance_km} km"
                    )

    # Display the map and capture click events
    # Normal mode map
    map_data_returned = st_folium(m, use_container_width=True, height=400)

    # Handle marker clicks to select a hotspot
    if map_data_returned.get("last_object_clicked"):
        clicked_data = map_data_returned["last_object_clicked"]
        if clicked_data and "lat" in clicked_data and "lng" in clicked_data:
            clicked_lat = clicked_data["lat"]
            clicked_lng = clicked_data["lng"]

            # Check if this click is different from current selection
            current_selection = st.session_state.get("selected_hotspot")
            if (
                not current_selection
                or abs(current_selection["lat"] - clicked_lat) > 0.0001
                or abs(current_selection["lon"] - clicked_lng) > 0.0001
            ):

                st.session_state.selected_hotspot = {
                    "lat": clicked_lat,
                    "lon": clicked_lng,
                }
                st.rerun()


# Check if we're in fullscreen mode - if so, stop here and don't show the rest
if st.session_state.get("map_fullscreen", False):
    st.stop()


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
