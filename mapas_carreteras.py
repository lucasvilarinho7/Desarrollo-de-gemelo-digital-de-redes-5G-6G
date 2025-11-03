import osmnx as ox

place = "Chamberí, Madrid"
G = ox.graph_from_place(place, network_type='drive', simplify=False)
#ox.plot_graph(G, node_color="r", node_size=20)
# ox.save_graph_geopackage(G, filepath="chamberi_roads.gpkg")
"""La linea anterior guarda el grafo en un archivo geopackage para usarlo despues de la forma
grafico = ox.load_graph_geopackage("chamberi_roads.gpkg")
"""

orig,d = ox.distance.nearest_nodes(G,X=-3.70860, Y=40.43818,return_dist=True) # En OSMNX las coordenadas van en el orden X=longitud, Y=latitud
dest = ox.distance.nearest_nodes(G,X=-3.69940, Y=40.44400)
print(f"Distancia del origen a su nodo más cercano: {d}")
route = ox.shortest_path(G, orig, dest, weight='length')
ox.plot_graph_route(G, route, route_color="green", orig_dest_size=40, node_size=0)


# edge_centrality = nx.closeness_centrality(nx.line_graph(G))
# nx.set_edge_attributes(G, edge_centrality, "edge_centrality")
# ec = ox.plot.get_edge_colors_by_attr(G, "edge_centrality", cmap="inferno")
# fig, ax = ox.plot_graph(G, edge_color=ec, edge_linewidth=3, node_size=5)