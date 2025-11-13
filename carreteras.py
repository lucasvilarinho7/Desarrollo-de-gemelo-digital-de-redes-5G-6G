import osmnx as ox
import networkx as nx
import matplotlib.pyplot as plt
import math
from geopy.distance import distance
from geopy import Point
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point



def graph_generator():

    print("Descargando red vial de Madrid desde OpenStreetMap...")
    G_osm = ox.graph_from_place("Chamberí, Madrid", network_type='drive', simplify=True)
    
    # Leer estaciones
    df_stations = pd.read_csv("./Datos/NR_stations_chamberí.csv")          
    for i, row in enumerate(df_stations.itertuples(), start=1):
        # Todo esta formateado a (lon,lat) para usar OSMNx siendo x=lon, y=lat
        G_osm.add_node(f"A_{i}", x=row.lon, y=row.lat, type="antenna", range=row.range)
    
    print(f"Grafo base cargado con {len(G_osm)} nodos y {len(G_osm.edges)} aristas.")
    
    return G_osm


def find_nearest_antenna_node(G, lat, lon):
    
    
    # Crear un subgrafo con solo los nodos de los tipos antenna y dron
    antenna_nodes = [n for n in G.nodes if G.nodes[n].get("type") in ["antenna", "dron"]]
    antenna_subgraph = G.subgraph(antenna_nodes)

    # Encontrar el nodo más cercano en el subgrafo
    nearest_node, min_dist = ox.distance.nearest_nodes(antenna_subgraph, lon, lat, return_dist=True) # En OSMNX las coordenadas van en el orden X=longitud, Y=latitud, solo sirve para grafos OSMNX

    return nearest_node, min_dist


def find_nearest_static_antenna_node(G, lat, lon):
    
    # Crear un subgrafo con solo los nodos del tipo antenna 
    antenna_nodes = [n for n in G.nodes if G.nodes[n].get("type") == "antenna"]
    antenna_subgraph = G.subgraph(antenna_nodes)

    # Encontrar el nodo más cercano en el subgrafo
    nearest_node, min_dist = ox.distance.nearest_nodes(antenna_subgraph, lon, lat, return_dist=True) # En OSMNX las coordenadas van en el orden X=longitud, Y=latitud, solo sirve para grafos OSMNX
    
    return nearest_node, min_dist

def check_route(G, id_vehicle, lat, lon):
    
    print(f"Ruta de {id_vehicle}:")
    start_lat, start_lon = G.nodes[id_vehicle]["y"],G.nodes[id_vehicle]["x"]
    node_start, dist_start = find_nearest_antenna_node(G, start_lat, start_lon)

    if G.nodes[node_start]["range"] < dist_start:
        dist_eff = dist_start - G.nodes[node_start]["range"]
        G, last_node = agile_deployment(G, node_start, start_lat, start_lon, dist_eff)
        G.add_edge(last_node, id_vehicle)

    node_end, dist_end = find_nearest_antenna_node(G, lat, lon)
    if G.nodes[node_end]["range"] < dist_end:
        dist_eff = dist_end - G.nodes[node_end]["range"]
        G, last_node = agile_deployment(G, node_end, lat, lon, dist_eff)
        G.remove_node(id_vehicle)
        G.add_node(id_vehicle,y=lat,x=lon,type="vehicle")
        G.add_edge(last_node, id_vehicle)
    else:
        G.remove_node(id_vehicle)
        G.add_node(id_vehicle, y=lat, x=lon, type="vehicle")
        G.add_edge(node_end, id_vehicle)
        
        
    
    return G

def agile_deployment(G, node_start, lat, lon, dist):
    
    dron_range = 50 # Para hacer la prueba en un distrito ponemos un area de cobertura baja para así poder ver como se produce un despliegue de varios drones
    n_drones = int(dist // dron_range)
    print(f"Desplegando {n_drones} drones para cubrir {dist:.1f} m.")

    start_lat, start_lon = G.nodes[node_start]["y"], G.nodes[node_start]["x"]
    start_point = Point(start_lat, start_lon)
    end_point = Point(lat, lon)

    delta_lon = math.radians(end_point.longitude - start_point.longitude)
    lat1, lat2 = math.radians(start_point.latitude), math.radians(end_point.latitude)
    x = math.sin(delta_lon) * math.cos(lat2)
    y = math.cos(lat1)*math.sin(lat2) - math.sin(lat1)*math.cos(lat2)*math.cos(delta_lon)
    bearing = (math.degrees(math.atan2(x, y)) + 360) % 360

    last_node = node_start
    for i in range(1, n_drones + 1):
        offset = G.nodes[node_start]["range"] + dron_range * i
        new_point = distance(meters=offset).destination(start_point, bearing)
        new_lat, new_lon = new_point.latitude, new_point.longitude
        new_id = f"D_T_{len([n for n in G.nodes if G.nodes[n].get('type') == 'dron']) + 1}"
        G.add_node(new_id, x=new_lon, y=new_lat, type="dron", range=dron_range)
        G.add_edge(last_node, new_id)
        last_node = new_id
        print(f"  - Dron {new_id} desplegado en ({new_lat:.6f}, {new_lon:.6f})")
    return G, last_node


def static_deployment(G, lat, lon, type, range):
    if type == "antenna":
        id_ = f"A_{len([n for n in G.nodes if G.nodes[n].get('type') == 'antenna']) + 1}"
    elif type == "dron":
        id_ = f"D_S_{len([n for n in G.nodes if G.nodes[n].get('type') == 'dron']) + 1}"
    else:
        id_ = f"V_{len([n for n in G.nodes if G.nodes[n].get('type') == 'vehicle']) + 1}"
    G.add_node(id_, x=lon, y=lat, type=type, range=range)
    print(f"Nuevo nodo {id_} ({type}) añadido.")
    return G


def remove_node(G, node_id):
    if node_id in G.nodes:
        G.remove_node(node_id)
        print(f"Nodo {node_id} eliminado.")
    else:
        print("Nodo no encontrado.")
    return G


def update_topology(G):
    drones_temp = [n for n in G.nodes if n.startswith("D_T_")]
    G.remove_nodes_from(drones_temp)
    print("Topología actualizada: drones temporales eliminados.")
    return G



def visualize_graph(G):
    

    pos = {}
    for n in G.nodes:
        data = G.nodes[n]
        pos[n] = (data["x"], data["y"])
    
    # Colores según tipo
    node_colors = []
    node_sizes = []
    for n in G.nodes:
        ntype = G.nodes[n].get("type")
        if ntype == "antenna":
            node_colors.append("red")
            node_sizes.append(100)
        elif ntype == "vehicle":
            node_colors.append("green")
            node_sizes.append(100)
        elif ntype == "dron":
            node_colors.append("skyblue")
            node_sizes.append(100)
        else:
            # Nodos de OSM (sin "type")
            node_colors.append("black")
            node_sizes.append(10)

    # Dibujar el grafo base de Madrid
    # base_graph = ox.graph_from_place("Chamberí, Madrid", network_type="drive")
    fig, ax = ox.plot_graph(G, show=False, close=False, bgcolor="white")

    # Dibujar tu grafo personalizado encima
    nx.draw(
        G, pos, ax=ax,
        with_labels=True,
        labels={n: n for n in G.nodes if "type" in G.nodes[n]},  # solo etiquetas para nodos personalizados
        node_color=node_colors,
        node_size=node_sizes,
        edge_color="orange",
        font_size=8,
        font_color="black"
    )

    plt.title("Red OSMnx (Distrtio) + Estaciones", fontsize=12)
    plt.show()      

    return G



def get_input_or_exit(prompt, cast_func=None):
    user_input = input(prompt)
    if user_input.lower() == "x":
        raise KeyboardInterrupt
    if cast_func:
        try:
            return cast_func(user_input)
        except ValueError:
            print("Entrada no válida. Intenta de nuevo o pulsa 'x' para volver al menú.")
            return get_input_or_exit(prompt, cast_func)
    return user_input


if __name__ == "__main__":
    
    G = graph_generator()

    while True:
        print("\n===== MENÚ =====")
        print("1. Visualizar grafo")
        print("2. Añadir nuevo nodo")
        print("3. Eliminar nodo")
        print("4. Calcular distancia entre dos nodos")
        print("5. Realizar ruta")
        print("6. Actualizar topología")
        print("7. Información nodo")
        print("8. Salir")
        print("(Pulsa 'x' para volver al menú en cualquier paso)")

        try:
            choice = get_input_or_exit("Selecciona una opción: ")

            if choice == "1":
                visualize_graph(G)

            elif choice == "2":
                lat = get_input_or_exit("Latitud: ", float)
                lon = get_input_or_exit("Longitud: ", float)
                type = get_input_or_exit("Tipo (antenna/vehicle/dron): ").lower()
                r = 0 if type == "vehicle" else 500 if type == "dron" else get_input_or_exit("Rango (m): ", int)
                G = static_deployment(G, lat, lon, type, r)

            elif choice == "3":
                print([n for n in G.nodes if G.nodes[n].get("type") in ["vehicle", "antenna"]])
                node_id = get_input_or_exit("ID a eliminar: ")
                G = remove_node(G, node_id)

            elif choice == "4":
                print([n for n in G.nodes if G.nodes[n].get("type") in ["vehicle", "antenna", "dron"]])
                n1 = get_input_or_exit("Nodo 1: ")
                n2 = get_input_or_exit("Nodo 2: ")
                if n1 in G and n2 in G:
                    
                    # Calcular la longitud total de la ruta
                    route = nx.shortest_path(G, n1, n2, weight='length')
                    route_length = sum(ox.utils_graph.get_route_edge_attributes(G, route, 'length'))
                    print(f"Distancia por carretera: {route_length:.2f} m")
                else:
                    print("Nodo no encontrado.")

            elif choice == "5":
                
                if(not ([n for n in G.nodes if G.nodes[n].get("type")=="vehicle"])):
                    
                    print("No hay vehículos")
                    break
                else:
                    print([n for n in G.nodes if G.nodes[n].get("type")=="vehicle"])
                    id_vehicle = get_input_or_exit("ID del vehículo: ")
                    lat = get_input_or_exit("Latitud destino: ", float)
                    lon = get_input_or_exit("Longitud destino: ", float)
                    G = check_route(G, id_vehicle, lat, lon)
                    visualize_graph(G)

            elif choice == "6":
                G = update_topology(G)
                print("La topología se ha actualizado")

            elif choice == "7":
                print([n for n in G.nodes if G.nodes[n].get("type") in ["vehicle", "antenna", "dron"]])
                node_id = get_input_or_exit("Nodo: ")
                print(G.nodes[node_id] if node_id in G else "No existe.")

            elif choice == "8":
                print("Saliendo...")
                break

            else:
                print("Opción inválida.")

        except KeyboardInterrupt:
            print("\nVolviendo al menú principal...\n")
            continue
