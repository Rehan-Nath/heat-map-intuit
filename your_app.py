import pandas as pd
import h3.api.basic_int as h3 
from dash import Dash, dcc, html, Input, Output, State
import plotly.graph_objects as go
import plotly.express as px
import numpy as np
import datetime
import re

df = pd.read_csv("route_data_final.csv", parse_dates=["datetime"])
df["dayName"] = df["datetime"].dt.day_name()


app = Dash(__name__)
server = app.server
app.layout = html.Div([
    html.Div([
        html.Div([
            html.Label("Date Range", style={"fontWeight": "bold", "fontSize": "12px"}),
            dcc.DatePickerRange(
                id="date-picker",
                start_date=datetime.date(2025, 5, 1),
                end_date=df["datetime"].max().date(),
                display_format="YYYY-MM-DD",
                style={"width": "100%"}
            )
        ], style={"width": "150px"}),

        html.Div([
            html.Label("Time Range (Hours)", style={"fontWeight": "bold", "fontSize": "12px"}),
            dcc.RangeSlider(
                id="time-slider", min=0, max=23.5, step=0.5,
                value=[6, 20],
                marks={i: f"{i}:00" for i in range(0, 24, 3)},
                tooltip={"placement": "bottom"}
            )
        ], style={"width": "300px"}),

        html.Div([
            html.Label("Weekdays", style={"fontWeight": "bold", "fontSize": "12px"}),
            dcc.Dropdown(
                id="day-filter",
                options=[{"label": d, "value": d} for d in df["dayName"].unique()],
                value=df["dayName"].unique().tolist(),
                multi=True,
                placeholder="Select weekdays",
            )
        ], style={"width": "160px"}),

        html.Div([
            html.Label("Direction", style={"fontWeight": "bold", "fontSize": "12px"}),
            dcc.Dropdown(
                id="direction-filter",
                options=[{"label": dir, "value": dir} for dir in df["inboundOutbound"].unique()],
                value=df["inboundOutbound"].unique().tolist(),
                multi=True,
                placeholder="Select directions",
            )
        ], style={"width": "150px"}),

        html.Div([
            html.Label("Ride Type", style={"fontWeight": "bold", "fontSize": "12px"}),
            dcc.Dropdown(
                id="type-filter",
                options=[{"label": t, "value": t} for t in df["Type"].unique()],
                value="Near Demand",
                multi=False,
                placeholder="Select type",
            )
        ], style={"width": "130px"}),

        html.Div([
            html.Label("Vehicle", style={"fontWeight": "bold", "fontSize": "12px"}),
            dcc.Dropdown(
                id="vehicle-filter",
                options=[{"label": "All", "value": "ALL"}] + [{"label": v, "value": v} for v in df["busNumber"].unique()],
                value=["ALL"],
                multi=True,
                placeholder="Select vehicles",
            )
        ], style={"width": "110px"}),

        html.Div([
            html.Label("Hex Resolution", style={"fontWeight": "bold", "fontSize": "12px"}),
            dcc.Dropdown(
                id="resolution-dropdown",
                options=[{"label": f"Res {i}", "value": i} for i in range(5, 11)],
                value=7,
                placeholder="Select hex size",
            )
        ], style={"width": "110px"}),

        html.Div([
            html.Label(" ", style={"fontSize": "12px"}),
            html.Button("Refresh", id="refresh-button", n_clicks=0, style={
                "width": "100%", "height": "38px", "marginTop": "5px"
            })
        ], style={"width": "100px"})
    ], style={
        "display": "flex",
        "flexWrap": "wrap",
        "gap": "15px",
        "marginBottom": "20px",
        "alignItems": "flex-end",
        "padding": "0px 20px"
    }),

    dcc.Graph(id="h3-map")
], style={"fontFamily": "Arial, sans-serif", "padding": "20px"})

@app.callback(
    Output("h3-map", "figure"),
    State("date-picker", "start_date"),
    State("date-picker", "end_date"),
    State("time-slider", "value"),
    State("day-filter", "value"),
    State("direction-filter", "value"),
    State("type-filter", "value"),
    State("vehicle-filter", "value"),
    State("resolution-dropdown", "value"),
    Input("refresh-button", "n_clicks")  
)
def update_map(start_date, end_date, time_range, days, directions, type_value, vehicles, resolution, n_clicks):
    start_hour, end_hour = time_range
    df_filtered = df[
        (df["datetime"].dt.date >= pd.to_datetime(start_date).date()) &
        (df["datetime"].dt.date <= pd.to_datetime(end_date).date()) &
        (df["datetime"].dt.hour >= start_hour) &
        (df["datetime"].dt.hour <= end_hour) &
        (df["dayName"].isin(days)) &
        (df["inboundOutbound"].isin(directions)) &
        (df["Type"] == type_value) &
        (True if "ALL" in vehicles else df["busNumber"].isin(vehicles))
    ].copy()

    df_filtered["h3_index"] = df_filtered.apply(
        lambda row: h3.latlng_to_cell(row["lat"], row["lon"], resolution)
        if pd.notnull(row["lat"]) and pd.notnull(row["lon"]) else None,
        axis=1
    )
    df_filtered = df_filtered[df_filtered["h3_index"].notnull()]
    grouped = df_filtered.groupby("h3_index").size().reset_index(name="count")

    fig = go.Figure()
    color_scale = px.colors.diverging.RdYlGn

    grouped["log_count"] = np.log1p(grouped["count"])
    max_log = grouped["log_count"].max()
    min_log = grouped["log_count"].min()

    if max_log == min_log:
        max_log += 1e-6

    hex_count_map = dict(zip(grouped["h3_index"], grouped["log_count"]))

    all_hexes = list(set(
        h3.latlng_to_cell(row["lat"], row["lon"], resolution)
        for _, row in df.iterrows()
        if pd.notnull(row["lat"]) and pd.notnull(row["lon"])
    ))

    def hex_to_rgba(color, alpha=0.8):
        if color.startswith("rgba"):
            return color
        elif color.startswith("rgb("):
            r, g, b = map(int, re.findall(r'\d+', color))
            return f"rgba({r},{g},{b},{alpha})"
        elif color.startswith("#") and len(color) == 7:
            h = color.lstrip('#')
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            return f"rgba({r},{g},{b},{alpha})"
        else:
            return "rgba(200,200,200,0.1)"

    for cell in all_hexes:
        try:
            boundary = h3.cell_to_boundary(cell)
        except Exception:
            continue

        pairs = [(lon, lat) for lat, lon in boundary]
        pairs.append(pairs[0])
        lons, lats = zip(*pairs)

        log_count = hex_count_map.get(cell, 0)
        if log_count == 0:
            fillcolor = "rgba(200,200,200,0.1)"
        else:
            norm_count = (log_count - min_log) / (max_log - min_log) if max_log != min_log else 0
            color_index = int(norm_count * (len(color_scale) - 1))
            fillcolor = hex_to_rgba(color_scale[color_index], alpha=0.4)

        fig.add_trace(go.Scattermap(
            lon=lons, lat=lats,
            mode="lines", fill="toself",
            fillcolor=fillcolor,
            line=dict(width=1, color="black"),
            hoverinfo="text",
            text=f"{int(np.expm1(log_count))} rides" if log_count > 0 else "0 rides",
            showlegend=False
        ))

    intuit_b5_lat = 37.4019
    intuit_b5_lon = -122.1107
    fig.add_trace(go.Scattermap(
        lat=[intuit_b5_lat],
        lon=[intuit_b5_lon],
        mode="markers+text",
        marker=dict(size=12, color="red"),
        text=["Intuit B5"],
        textposition="top right",
        hoverinfo="text",
        showlegend=False
    ))

    fig.update_layout(
        map=dict(
            style="carto-positron",  #"open-street-map", "carto-darkmatter"
            center={"lat": 37.4019, "lon": -122.1107},
            zoom=9
        ),
        margin={"r": 0, "t": 30, "l": 0, "b": 0},
        height=580,
        showlegend=False,
        uirevision='true'
    )
    return fig

if __name__ == "__main__":
    app.run(debug=True)
