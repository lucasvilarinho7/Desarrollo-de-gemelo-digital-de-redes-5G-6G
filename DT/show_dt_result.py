import networkx as nx
import matplotlib.pyplot as plt


def load_graph_with_real_positions(graphml_path):
    """
    Carga un GraphML y extrae:
    - Grafo
    - Posiciones reales (con sistema de pantalla)
    - Tipos de nodo
    """
    G = nx.read_graphml(graphml_path)

    pos_raw = {}
    node_types = {}

    for node, data in G.nodes(data=True):
        try:
            x = float(data.get("pos_x", 0))
            y = float(data.get("pos_y", 0))
        except ValueError:
            x, y = 0, 0

        pos_raw[node] = (x, y)
        node_types[node] = data.get("node_type", "unknown")

    return G, pos_raw, node_types


def invert_y_axis(pos_raw):
    """
    Convierte coordenadas con origen arriba-izquierda
    al sistema de matplotlib (origen abajo-izquierda)
    """
    # Obtener altura máxima
    max_y = max(y for _, y in pos_raw.values())

    pos = {}
    for node, (x, y) in pos_raw.items():
        pos[node] = (x, max_y - y)

    return pos


def draw_graph(G, pos, node_types):
    plt.figure(figsize=(8, 8))

    ue_nodes = [n for n, t in node_types.items() if t == "ue"]
    gnb_nodes = [n for n, t in node_types.items() if t == "gnb"]

    nx.draw_networkx_nodes(G, pos,
                           nodelist=ue_nodes,
                           node_size=80,
                           label="UE")

    nx.draw_networkx_nodes(G, pos,
                           nodelist=gnb_nodes,
                           node_size=300,
                           node_shape='s',
                           label="gNB")

    nx.draw_networkx_edges(G, pos, alpha=0.4)
    nx.draw_networkx_labels(G, pos, font_size=8)

    plt.title("Topología (coordenadas con origen arriba-izquierda)")
    plt.xlabel("X")
    plt.ylabel("Y")
    plt.axis("equal")
    plt.legend()
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":

    graphml_file = "coverage_results/digital_twin_20260226_180441.graphml"

    G, pos_raw, node_types = load_graph_with_real_positions(graphml_file)
    pos = invert_y_axis(pos_raw)
    draw_graph(G, pos, node_types)

