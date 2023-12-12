import country_converter as coco
import plotly.express as px
import plotly.io as pio

layout = {"plot_bgcolor": "black", "paper_bgcolor": "black", "font": {"color": "white"}}
geo_layout = {
    "showcountries": True,
    "countrycolor": "white",
    "showocean": True,
    "oceancolor": "black",
    "showland": True,
    "landcolor": "gray",
    "bgcolor": "black",
    "showlakes": False,
}


def draw_pie(data, title):
    """
    Creates a pie chart from the given data and saves it to the given filename.

    :param data: A list of dictionaries with the keys "label" and "size".
    :param title: The title of the chart.

    :return: The figure object.
    """
    fig = px.pie(data, values="size", names="label", title=title)
    fig.update_layout(layout)
    return fig


def draw_bar(data, title):
    """
    Creates a bar chart from the given data and saves it to the given filename.

    :param data: A list of dictionaries with the keys "label" and "size".
    :param title: The title of the chart.

    :return: The figure object.
    """
    fig = px.bar(data, x="label", y="size", title=title)
    fig.update_layout(layout)
    return fig


def draw_map(data, title):
    """
    Creates a map from the given data and saves it to the given filename.

    :param data: A list of dictionaries with the keys "label", "size", "lat" and "lon".
    :param title: The title of the chart.

    :return: The figure object.
    """
    fig = px.scatter_geo(
        data,
        lat="lat",
        lon="lon",
        size="size",
        hover_name="label",
        title=title,
        projection="natural earth",
    )
    fig.update_layout(layout)
    fig.update_geos(
        **geo_layout,
    )
    return fig


def draw_choropleth(data, title):
    """
    Creates a choropleth from the given data and saves it to the given filename.

    :param data: A list of dictionaries with the keys "label", "size", "ISO-3".
    :param title: The title of the chart.

    :return: The figure object.
    """
    fig = px.choropleth(
        data,
        locations="ISO-3",
        color="size",
        hover_name="label",
        title=title,
        projection="natural earth",
    )
    fig.update_layout(layout)
    fig.update_geos(
        **geo_layout,
    )
    return fig


def draw_geoheatmap(data, title, hover_data=None):
    """
    Creates a geoheatmap from the given data and saves it to the given filename.

    :param data: A list of dictionaries with the keys "label", "size", "lat" and "lon".
    :param title: The title of the chart.
    :param hover_data: The data to show when hovering over a point.

    :return: The figure object.
    """
    fig = px.density_mapbox(
        data,
        lat="lat",
        lon="lon",
        z="size",
        hover_name="label",
        hover_data=hover_data,
        title=title,
        radius=10,
        zoom=1,
        mapbox_style="carto-darkmatter",
    )
    fig.update_layout(layout)
    return fig


def draw_scatter(data, title):
    """
    Creates a scatter plot from the given data and saves it to the given filename.

    :param data: A list of dictionaries with the keys "label", "size", "x" and "y".
    :param title: The title of the chart.

    :return: The figure object.
    """
    fig = px.scatter(
        data,
        x="x",
        y="y",
        size="size",
        hover_name="label",
        title=title,
    )
    fig.update_layout(layout)
    fig.update_geos(
        **geo_layout,
    )
    return fig


def save_graphs_html(*graphs, filename):
    """
    Saves the given graphs to the given filename.

    :param graphs: The graphs to save.
    :param filename: The filename to save the graphs to.

    :return: None
    """
    if any(
        (
            not filename.endswith(".html"),
            len(graphs) == 0,
        )
    ):
        raise ValueError("Bad filename or graphs")

    with open(filename, "w") as f:
        f.write("<html>")
        f.write(
            """
<head>
    <style>
    div {
        background-color: black;
    }
    </style>
    <title>Very Awsome Graphs</title>
</head>"""
        )
        f.write('<body style="background-color: black;">')
        for graph in graphs:
            graph.update_layout(layout)
            f.write(pio.to_html(graph, include_plotlyjs="cdn", full_html=False))
        f.write("</body></html>")


def iso2_to_3(*before):
    return coco.convert(names=before, to="ISO3")
