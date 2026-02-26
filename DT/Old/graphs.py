import networkx as nx
import matplotlib.pyplot as plt
import math
from geopy.distance import geodesic, distance
from geopy import Point


def graph_generator():


    # Aquí iría parte de leer los csv y crear los nodos del grafo a partir de esos datos.

    A_1 = [40.4168, -3.7038]
    A_2 = [40.4258, -3.7038]
    V_1 = [40.4300, -3.6200]

    G = nx.Graph()
    
    G.add_node("A_1", pos=(A_1[0], A_1[1]), type="antenna", range=1500)
    G.add_node("A_2", pos=(A_2[0], A_2[1]), type="antenna", range=2000)
    G.add_node("V_1", pos=(V_1[0], V_1[1]), type="vehicle")
    
    G.add_edge("A_1", "A_2")
    
    
    return G


def check_route(G,id_vehicle,lat,lon):
    # Se podría comprobar si tiene neighbors para ver si inicia si está sin cobertura
    
    print(f"La posición objetivo de {id_vehicle} es: ({lat}, {lon})")
    print(f'La posición inicial de {id_vehicle} es: ({G.nodes[id_vehicle]["pos"][0]}, {G.nodes[id_vehicle]["pos"][1]})')
    
    
    # Comprobar si el nodo inicial está dentro del rango de cobertura del nodo más cercano o si hay que hacer un despliegue previo
    node_start, distance_start = find_nearest_antenna_node(G, G.nodes[id_vehicle]["pos"][0], G.nodes[id_vehicle]["pos"][1]) 
    print("La distancia al nodo inicial:",distance_start)
    
    
    
    if(G.nodes[node_start]["range"] < distance_start):
        distance_effective = distance_start - G.nodes[node_start]["range"] # Tenemos en cuenta el rango de cobertura del nodo más cercano
        G,last_node = agile_deployment(G, node_start, G.nodes[id_vehicle]["pos"][0], G.nodes[id_vehicle]["pos"][1], distance_effective)
        G.add_edge(last_node, id_vehicle)
        
        print("Despliegue previo a realizar la ruta")
        visualize_graph(G)
    
        # Comprobar si el nodo final está dentro del rango de cobertura del nodo más cercano o si hay que hacer un despliegue previo
        node_end,distance_end = find_nearest_antenna_node(G, lat, lon)
        print("La distancia al nodo final:",distance_end)
        if(G.nodes[node_end]["range"] < distance_end):
            distance_effective = distance_end - G.nodes[node_end]["range"] # Tenemos en cuenta el rango de cobertura del nodo más cercano
            G,last_node = agile_deployment(G, node_end, lat, lon, distance_effective)
            # Conectar el nodo objetivo al último nodo desplegado y actualizar el grafo
            G.remove_node(id_vehicle)
            G.add_node(id_vehicle, pos=(lat, lon), type="vehicle")
            G.add_edge(last_node, id_vehicle)
            
            return G
        
        else:   
            
            G.remove_node(id_vehicle)
            G.add_node(id_vehicle, pos=(lat, lon), type="vehicle")
            G.add_edge(node_end, id_vehicle)
        
            return G
            
    
    else:
        
        # Comprobar si el nodo final está dentro del rango de cobertura del nodo más cercano o si hay que hacer un despliegue previo
        node_end,distance_end = find_nearest_antenna_node(G, lat, lon)
        print("La distancia al nodo final:",distance_end)
        if(G.nodes[node_end]["range"] < distance_end):

            distance_effective= distance_end -G.nodes[node_end]["range"] # Tenemos en cuenta el rango de cobertura del nodo más cercano
            G_updated,last_node = agile_deployment(G, node_end, lat, lon, distance_effective)
            
            # Conectar el nodo objetivo al último nodo desplegado y actualizar el grafo
            G_updated.remove_node(id_vehicle)
            G_updated.add_node(id_vehicle, pos=(lat, lon), type="vehicle")
            G_updated.add_edge(last_node, id_vehicle)
            
            return G_updated
        
        else:
            # Conectar el nodo objetivo al último nodo desplegado y actualizar el grafo
            G.remove_node(id_vehicle)
            G.add_node(id_vehicle, pos=(lat, lon), type="vehicle")
            G.add_edge(node_end, id_vehicle)
        
            return G
    

def agile_deployment(G, node_objective, lat, lon, dist):

    dron_range = 500  # Rango máximo de cobertura de cada dron en metros
    n_nodes_to_deploy = int(dist // dron_range)
    print("Número de nodos a desplegar:",n_nodes_to_deploy)
    
    # Obtener las coordenadas del nodo de partida y de la posición final objetivo.
    start_lat, start_lon = G.nodes[node_objective]["pos"][0], G.nodes[node_objective]["pos"][1]
    start_point = Point(start_lat, start_lon)
    end_point = Point(lat, lon)

    # Calcular rumbo (bearing) entre ambos puntos
    delta_lon = math.radians(end_point.longitude - start_point.longitude)
    lat1 = math.radians(start_point.latitude)
    lat2 = math.radians(end_point.latitude)
    x = math.sin(delta_lon) * math.cos(lat2)
    y = math.cos(lat1)*math.sin(lat2) - math.sin(lat1)*math.cos(lat2)*math.cos(delta_lon)
    bearing = (math.degrees(math.atan2(x, y)) + 360) % 360

    last_node = node_objective
    
    for i in range(1, n_nodes_to_deploy + 1):
        offset = G.nodes[node_objective]["range"] + dron_range * i # Tenemos en cuenta el rango del nodo de partida, par comenzar a partir de ahí a hacer el despliegue
        new_point = distance(meters=offset).destination(start_point, bearing)
        new_lat, new_lon = new_point.latitude, new_point.longitude
        # new_node_id = f"D_T_{id_vehicle}_{i}" Esto para el caso de querer independencia entre varios vehículos, así podemos diferenciar los drones desplegados para cada uno
        new_node_id = f"D_T_{len([n for n in G.nodes if G.nodes[n].get('type') == 'dron']) + 1}"
        G.add_node(new_node_id, pos=(new_lat, new_lon), type="dron", range=dron_range)
        G.add_edge(last_node, new_node_id)
        print(f"Nuevo nodo {new_node_id} en ({new_lat:.6f}, {new_lon:.6f})")
        last_node = new_node_id


    return G,last_node


def static_deployment(G, lat, lon, type, range):
    
    
    if(type == "antenna"):
        id_antenna = f"A_{len([n for n in G.nodes if G.nodes[n].get('type') == 'antenna']) + 1}"
        n_node,distance_n_node = find_nearest_static_antenna_node(G, lat, lon)
        
        if(G.nodes[n_node]["range"] > distance_n_node or range > distance_n_node):
            
            G.add_node(id_antenna, pos=(lat, lon), type=type, range=range)
            G.add_edge(n_node, id_antenna)
            
            return G
        else: 
            G.add_node(id_antenna, pos=(lat, lon), type=type)
            
            return G
            
    
    elif(type == "dron"):
        id_dron = f"D_S_{len([n for n in G.nodes if G.nodes[n].get('type') == 'dron']) + 1}"
        n_node,distance_n_node = find_nearest_static_antenna_node(G, lat, lon)
        
        if(G.nodes[n_node]["range"] > distance_n_node or range > distance_n_node):
            
            G.add_node(id_dron, pos=(lat, lon), type=type)
            G.add_edge(n_node, id_dron)
            
            return G
        else: 
            G.add_node(id_dron, pos=(lat, lon), type=type)
            
            return G
    
    else:
        id_vehicle = f"V_{len([n for n in G.nodes if G.nodes[n].get('type') == 'vehicle']) + 1}"
        G.add_node(id_vehicle, pos=(lat, lon), type=type)
        
        return G



def find_nearest_static_antenna_node(G, lat, lon): # Solo busca en los nodos de tipo 'antenna' 
    
    antenna_nodes = [n for n in G.nodes if G.nodes[n].get("type") == "antenna"]
    
    # Crear un subgrafo con solo los nodos de tipo 'antenna'
    #antenna_subgraph = G.subgraph(antenna_nodes)

    # Encontrar el nodo más cercano en el subgrafo
    #nearest_node = ox.distance.nearest_nodes(antenna_subgraph, lon, lat) # En OSMNX las coordenadas van en el orden X=longitud, Y=latitud, solo sirve para grafos OSMNX
    
    # Inicializar variables para el nodo más cercano
    nearest_node = None
    min_distance = float("inf")

    # Iterar sobre los nodos de tipo 'antenna' para encontrar el más cercano
    for node in antenna_nodes:
        node_lat, node_lon = G.nodes[node]["pos"][0], G.nodes[node]["pos"][1]
        distance = distance_meters((lat, lon), (node_lat, node_lon))
        if distance < min_distance:
            min_distance = distance
            nearest_node = node
            
    return nearest_node, min_distance


def find_nearest_antenna_node(G, lat, lon): 
    
    antenna_nodes = [n for n in G.nodes if G.nodes[n].get("type") in ["antenna", "dron"]]
    
    # Inicializar variables para el nodo más cercano
    nearest_node = None
    min_distance = float("inf")

    # Iterar sobre los nodos de tipo 'antenna' para encontrar el más cercano
    for node in antenna_nodes:
        node_lat, node_lon = G.nodes[node]["pos"][0], G.nodes[node]["pos"][1]
        distance = distance_meters((lat, lon), (node_lat, node_lon))
        if distance < min_distance:
            min_distance = distance
            nearest_node = node
            
    return nearest_node, min_distance


def distance_meters(coord1, coord2):


    R = 6371000  # Radio de la Tierra en metros
    lat1, lon1 = coord1
    lat2, lon2 = coord2

    # Convertir a radianes
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c  # distancia en metros

def visualize_graph(G):
    
    #pos = nx.spring_layout(G, seed=42)
    
    node_colors = ["red" if G.nodes[n].get("type") == "antenna" else "green" if G.nodes[n].get("type") == "vehicle" else "skyblue" for n in G.nodes]    
    pos = {n: (G.nodes[n]["pos"][1], G.nodes[n]["pos"][0]) for n in G.nodes()}  # lon, lat, con esta representación el último nodo se representa justo encima de la posicion final del vehículo
    nx.draw(G, pos, with_labels=True, node_color=node_colors, edge_color="gray", node_size=800)
    plt.title("Red dinámica inicial con NetworkX")
    plt.show()
    
    return G

def remove_node(G, node_id):
    if node_id in G.nodes:
        G.remove_node(node_id)
        print(f"Nodo {node_id} eliminado.")
    else:
        print("El nodo no existe en el grafo.")
    return G

def update_topology(G):
    drones_to_remove = [n for n in G.nodes 
                        if n.startswith("D_T_") and G.nodes[n].get('type') == 'dron']

    G.remove_nodes_from(drones_to_remove)
    
    visualize_graph(G)

    return G



def get_input_or_exit(prompt, cast_func=None):
    """Pide un input, si es 'x' vuelve al menú, si se indica cast_func, convierte el valor."""
    user_input = input(prompt)
    if user_input.lower() == "x":
        raise KeyboardInterrupt  # Se usa para romper y volver al menú
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
        print("3. Eliminar un nodo")
        print("4. Calcular distancia entre dos nodos")
        print("5. Realizar ruta")
        print("6. Actualizar topología")
        print("7. Información nodo")
        print("8. Salir")
        print("Pulsa 'x' en cualquier momento para volver al menú.")

        try:
            choice = get_input_or_exit("Selecciona una opción: ")

            if choice == "1":
                visualize_graph(G)

            elif choice == "2":
                lat = get_input_or_exit("Latitud: ", float)
                lon = get_input_or_exit("Longitud: ", float)
                type = get_input_or_exit("Tipo (antenna/vehicle/dron): ").lower()
                if type not in ["antenna", "vehicle", "dron"]:
                    print("Tipo de nodo no válido.")
                    continue
                if type == "vehicle":
                    r = 0
                elif type == "dron":
                    r = 500
                else:
                    r = get_input_or_exit("Rango en metros: ", int)
                G = static_deployment(G, lat, lon, type, r)
            
            elif choice == "3":
                print("Nodos disponibles:", list(G.nodes))
                node_id = get_input_or_exit("ID del nodo a eliminar: ")
                if node_id in G.nodes:
                    G = remove_node(G, node_id)
                else:
                    print("El nodo no existe en el grafo.")
                    
            elif choice == "4":
                print("Nodos disponibles:",G.nodes)
                n1 = get_input_or_exit("Nodo 1: ")
                n2 = get_input_or_exit("Nodo 2: ")
                if n1 in G.nodes and n2 in G.nodes:
                    coord1 = G.nodes[n1]["pos"]
                    coord2 = G.nodes[n2]["pos"]
                    dist = distance_meters(coord1, coord2)
                    print(f"Distancia entre {n1} y {n2}: {dist:.4f} m")
                else:
                    print("Uno o ambos nodos no existen en el grafo.")
            
            elif choice == "5":
                lat = get_input_or_exit("Latitud del destino: ", float)
                lon = get_input_or_exit("Longitud del destino: ", float)
                id_vehicle = get_input_or_exit("ID del vehículo: ")
                if id_vehicle not in G.nodes:
                    print("El ID del vehículo no existe en el grafo.")
                    continue
                else:
                    G = check_route(G, id_vehicle, lat, lon)
                    print("Ruta calculada y grafo actualizado.")
                    visualize_graph(G)
            
            elif choice == "6":
                G = update_topology(G)
                print("Topología actualizada.")
            
            elif choice == "7":
                print("Qué nodo deseas consultar:", list(G.nodes))
                node_id = get_input_or_exit("ID del nodo: ")
                if node_id in G.nodes:
                    print(G.nodes[node_id])            
                else:
                    print("El nodo no existe en el grafo.")
                
            elif choice == "8":
                print("Saliendo del programa.")
                break

            else:
                print("Opción no válida. Inténtalo de nuevo.")
        
        except KeyboardInterrupt:
            print("\nVolviendo al menú principal...\n")
            continue
