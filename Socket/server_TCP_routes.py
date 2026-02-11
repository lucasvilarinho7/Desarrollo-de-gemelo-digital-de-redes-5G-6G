import socket
import signal
import sys
import json
import time
import threading
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, LinearSegmentedColormap
from datetime import datetime
from collections import defaultdict

# ================= CONFIGURACIÓN GLOBAL =================

# --- Socket TCP ---
HOST = "0.0.0.0"
PORT = 50000

# --- Archivos ---
MOBILITY_XML = "../simu5g-wk/GNBrectilineo/simulations/mobility_routes.xml"
RESULTS_DIR = "./coverage_results"
PLOTS_DIR = "./coverage_plots"

# --- Área de simulación (debe coincidir con omnetpp.ini) ---
AREA_SIZE_X = 2000  # metros
AREA_SIZE_Y = 2000  # metros
GRID_CELL_SIZE = 50  # metros (celdas de 50x50m)

# --- Umbrales de cobertura ---
SINR_THRESHOLD_COVERAGE = 20  # dB - mínimo para considerar "con cobertura"

# Niveles de QoS según SINR
QOS_LEVELS = {
    'Excellent': 20,   # SINR >= 20 dB
    'Good': 13,        # 13 <= SINR < 20
    'Fair': 0,         # 0 <= SINR < 13
    'Poor': -10,       # -10 <= SINR < 0
    'No Service': -999 # SINR < -10
}

# --- Análisis ---
ENABLE_REALTIME_ANALYSIS = True  # Mostrar estadísticas en tiempo real
ANALYSIS_INTERVAL = 10.0  # segundos - cada cuánto mostrar estadísticas

ENABLE_REALTIME_PLOT = False  # Gráfico en tiempo real (consume recursos)
PLOT_UPDATE_INTERVAL = 10.0  # segundos

ENABLE_FINAL_REPORT = True  # Generar reporte completo al finalizar

# ================= ESTADO GLOBAL =================

route_already_modified = False
conn = None
addr = None
server_running = True

# ================= CLASE: GRID DE COBERTURA =================

class CoverageGrid:
    """
    Grid de cobertura con ORIGEN EN ESQUINA SUPERIOR IZQUIERDA
    Y crece hacia abajo (como imagen)
    """
    
    def __init__(self, area_size_x=AREA_SIZE_X, area_size_y=AREA_SIZE_Y, 
                 cell_size=GRID_CELL_SIZE):
        self.area_size_x = area_size_x
        self.area_size_y = area_size_y
        self.cell_size = cell_size
        
        # Calcular dimensiones del grid
        self.grid_cols = int(np.ceil(area_size_x / cell_size))
        self.grid_rows = int(np.ceil(area_size_y / cell_size))
        
        # Grid de cobertura (binario: 1=cubierto, 0=sin cobertura)
        self.coverage_map = np.zeros((self.grid_rows, self.grid_cols), dtype=int)
        
        # Grid de SINR (valores continuos)
        self.sinr_map = np.full((self.grid_rows, self.grid_cols), -999.0)
        
        # Grid de serving cell ID
        self.cell_id_map = np.full((self.grid_rows, self.grid_cols), -1, dtype=int)
        
        # Contador de mediciones por celda
        self.measurement_count = np.zeros((self.grid_rows, self.grid_cols), dtype=int)
        
        # Timestamp de última actualización
        self.last_update_time = None
        
        print(f"[CoverageGrid] Initialized: {self.grid_rows}x{self.grid_cols} cells "
              f"({self.grid_rows * self.grid_cols} total)")
        print(f"[CoverageGrid] Origin: TOP-LEFT corner (0, 0)")
    
    def position_to_grid(self, x, y):
        """
        Convierte coordenadas (x,y) a índices de grid (row, col)
        Con origin='upper' en matplotlib:
        - row 0 corresponde a Y=0 (arriba)
        - row aumenta hacia abajo
        """
        col = int(x / self.cell_size)
        row = int(y / self.cell_size)  # Sin inversión
        
        # Limitar a dimensiones del grid
        col = max(0, min(col, self.grid_cols - 1))
        row = max(0, min(row, self.grid_rows - 1))
        
        return row, col
    
    def update_from_ue_measurement(self, x, y, sinr, cell_id, timestamp):
        """Actualiza el grid con una medición de un UE"""
        row, col = self.position_to_grid(x, y)
        
        # Actualizar cobertura binaria
        if sinr >= SINR_THRESHOLD_COVERAGE:
            self.coverage_map[row, col] = 1
        else:
            self.coverage_map[row, col] = 0
        
        # Actualizar SINR (promedio móvil exponencial)
        if self.measurement_count[row, col] == 0:
            self.sinr_map[row, col] = sinr
        else:
            alpha = 0.3
            self.sinr_map[row, col] = (alpha * sinr + 
                                       (1 - alpha) * self.sinr_map[row, col])
        
        # Actualizar cell ID
        self.cell_id_map[row, col] = cell_id
        
        # Incrementar contador
        self.measurement_count[row, col] += 1
        
        # Actualizar timestamp
        self.last_update_time = timestamp
    
    def get_coverage_percentage(self):
        """Calcula el porcentaje de cobertura del área TOTAL"""
        total_cells = self.grid_rows * self.grid_cols
        covered_cells = np.sum(self.coverage_map)
        
        percentage = (covered_cells / total_cells) * 100
        return percentage
    
    def get_coverage_statistics(self):
        """Obtiene estadísticas detalladas de cobertura"""
        total_cells = self.grid_rows * self.grid_cols
        covered_cells = np.sum(self.coverage_map)
        uncovered_cells = total_cells - covered_cells
        
        # Células con mediciones
        measured_cells = np.sum(self.measurement_count > 0)
        unmeasured_cells = total_cells - measured_cells
        
        # SINR promedio en células cubiertas
        covered_sinr_values = self.sinr_map[self.coverage_map == 1]
        if len(covered_sinr_values) > 0:
            avg_sinr_covered = np.mean(covered_sinr_values)
            min_sinr_covered = np.min(covered_sinr_values)
            max_sinr_covered = np.max(covered_sinr_values)
        else:
            avg_sinr_covered = -999
            min_sinr_covered = -999
            max_sinr_covered = -999
        
        # NUEVO: Distribución por gNodeB SOLO EN CELDAS MEDIDAS
        gnb_distribution = {}
        for gnb_id in np.unique(self.cell_id_map):
            if gnb_id >= 0:  # Ignorar -1 (sin asignar)
                cells_served = np.sum(self.cell_id_map == gnb_id)
                gnb_distribution[int(gnb_id)] = {
                    'cells': int(cells_served),
                    'percentage': (cells_served / measured_cells * 100) if measured_cells > 0 else 0
                }
        
        stats = {
            'total_cells': total_cells,
            'covered_cells': int(covered_cells),
            'uncovered_cells': int(uncovered_cells),
            'coverage_percentage': (covered_cells / total_cells) * 100,
            'measured_cells': int(measured_cells),
            'unmeasured_cells': int(unmeasured_cells),
            'measurement_percentage': (measured_cells / total_cells) * 100,
            'avg_sinr_covered': float(avg_sinr_covered),
            'min_sinr_covered': float(min_sinr_covered),
            'max_sinr_covered': float(max_sinr_covered),
            'total_measurements': int(np.sum(self.measurement_count)),
            'gnb_distribution': gnb_distribution,
            'last_update': self.last_update_time
        }
        
        return stats
    
    def get_qos_distribution(self):
        """
        CORREGIDO: Calcula la distribución de niveles de QoS 
        SOLO EN CELDAS MEDIDAS (no en el total)
        """
        # Solo considerar celdas con mediciones
        measured_mask = self.measurement_count > 0
        total_measured_cells = np.sum(measured_mask)
        
        if total_measured_cells == 0:
            return {level: {'cells': 0, 'percentage': 0.0} 
                    for level in QOS_LEVELS.keys()}
        
        # Obtener solo valores SINR de celdas medidas
        measured_sinr = self.sinr_map[measured_mask]
        
        distribution = {}
        
        # Excellent: SINR >= 20
        excellent_count = np.sum(measured_sinr >= 20)
        distribution['Excellent'] = {
            'cells': int(excellent_count),
            'percentage': (excellent_count / total_measured_cells) * 100
        }
        
        # Good: 13 <= SINR < 20
        good_count = np.sum((measured_sinr >= 13) & (measured_sinr < 20))
        distribution['Good'] = {
            'cells': int(good_count),
            'percentage': (good_count / total_measured_cells) * 100
        }
        
        # Fair: 0 <= SINR < 13
        fair_count = np.sum((measured_sinr >= 0) & (measured_sinr < 13))
        distribution['Fair'] = {
            'cells': int(fair_count),
            'percentage': (fair_count / total_measured_cells) * 100
        }
        
        # Poor: -10 <= SINR < 0
        poor_count = np.sum((measured_sinr >= -10) & (measured_sinr < 0))
        distribution['Poor'] = {
            'cells': int(poor_count),
            'percentage': (poor_count / total_measured_cells) * 100
        }
        
        # No Service: SINR < -10
        no_service_count = np.sum(measured_sinr < -10)
        distribution['No Service'] = {
            'cells': int(no_service_count),
            'percentage': (no_service_count / total_measured_cells) * 100
        }
        
        return distribution
    
    def save_to_file(self, filename):
        """Guarda el estado del grid en un archivo JSON"""
        Path(RESULTS_DIR).mkdir(exist_ok=True)
        filepath = Path(RESULTS_DIR) / filename
        
        data = {
            'metadata': {
                'grid_rows': self.grid_rows,
                'grid_cols': self.grid_cols,
                'cell_size': self.cell_size,
                'area_size_x': self.area_size_x,
                'area_size_y': self.area_size_y,
                'origin': 'top-left',
                'timestamp': datetime.now().isoformat(),
                'last_update': self.last_update_time
            },
            'coverage_map': self.coverage_map.tolist(),
            'sinr_map': self.sinr_map.tolist(),
            'cell_id_map': self.cell_id_map.tolist(),
            'measurement_count': self.measurement_count.tolist(),
            'statistics': self.get_coverage_statistics(),
            'qos_distribution': self.get_qos_distribution()
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"[CoverageGrid] Saved to {filepath}")

# ================= CLASE: ANALIZADOR DE COBERTURA =================

class CoverageAnalyzer:
    """Analizador principal de cobertura"""
    
    def __init__(self):
        self.grid = CoverageGrid()
        self.ue_data = defaultdict(list)
        self.gnb_data = {}  # Almacena info de gNodeBs
        self.start_time = None
        
        print("[CoverageAnalyzer] Initialized")
    
    def process_ue_message(self, message):
        """Procesa un mensaje de UE (CSV o JSON)"""
        try:
            # Intentar parsear como JSON primero
            if message.strip().startswith('{'):
                data = json.loads(message)
                
                if data.get("type") != "POS":
                    return
                
                ue_id = data.get("ue_id")
                timestamp = data.get("timestamp")
                position = data.get("position", {})
                network = data.get("network", {})
                
                x = position.get("x", 0)
                y = position.get("y", 0)
                z = position.get("z", 0)
                sinr = network.get("sinr", -999)
                master_id = network.get("master_id", -1)
            
            else:
                # Parsear formato CSV: POS,timestamp,x,y,z,sinr,master_id
                parts = message.strip().split(',')
                
                if parts[0] != "POS" or len(parts) < 7:
                    return
                
                ue_id = "UE_0"
                timestamp = float(parts[1])
                x = float(parts[2])
                y = float(parts[3])
                z = float(parts[4])
                sinr = float(parts[5])
                master_id = int(parts[6])
            
            # Actualizar grid
            self.grid.update_from_ue_measurement(x, y, sinr, master_id, timestamp)
            
            # Almacenar medición del UE
            self.ue_data[ue_id].append({
                'timestamp': timestamp,
                'x': x,
                'y': y,
                'z': z,
                'sinr': sinr,
                'master_id': master_id
            })
            
            # Establecer start_time
            if self.start_time is None:
                self.start_time = timestamp
            
            return True
            
        except Exception as e:
            print(f"[CoverageAnalyzer] Error processing UE message: {e}")
            return False
    
    def process_coverage_message(self, message):
        """Procesa un mensaje de COVERAGE de gNodeB"""
        try:
            data = json.loads(message)
            
            if data.get("type") != "COVERAGE":
                return False
            
            gnb_id = data.get("gnb_id")
            gnb_index = data.get("gnb_index")
            timestamp = data.get("timestamp")
            position = data.get("position", {})
            connected_ues = data.get("connected_ues", [])
            num_connected = data.get("num_connected", 0)
            
            x = position.get("x", 0)
            y = position.get("y", 0)
            z = position.get("z", 0)
            
            print(f"\n[Servidor] 📡 COVERAGE UPDATE from gNodeB[{gnb_index}]")
            print(f"  Time: {timestamp:.2f}s")
            print(f"  Position: ({x:.1f}, {y:.1f}, {z:.1f})")
            print(f"  Connected UEs: {num_connected}")
            if connected_ues:
                print(f"  UE IDs: {connected_ues}")
            
            # Almacenar en el analizador
            if gnb_id not in self.gnb_data:
                self.gnb_data[gnb_id] = []
            
            self.gnb_data[gnb_id].append({
                'timestamp': timestamp,
                'index': gnb_index,
                'x': x,
                'y': y,
                'z': z,
                'connected_ues': connected_ues,
                'num_connected': num_connected
            })
            
            return True
            
        except json.JSONDecodeError:
            print("[CoverageAnalyzer] Error: JSON inválido en mensaje COVERAGE")
            return False
        except Exception as e:
            print(f"[CoverageAnalyzer] Error processing COVERAGE message: {e}")
            return False
    
    def get_summary_report(self):
        """Genera un reporte resumen"""
        stats = self.grid.get_coverage_statistics()
        qos = self.grid.get_qos_distribution()
        
        num_ues = len(self.ue_data)
        total_measurements = sum(len(measurements) 
                                for measurements in self.ue_data.values())
        
        elapsed_time = None
        if self.start_time and self.grid.last_update_time:
            elapsed_time = self.grid.last_update_time - self.start_time
        
        # Información de gNodeBs
        gnb_info = {}
        for gnb_id, records in self.gnb_data.items():
            if records:
                latest = records[-1]
                gnb_info[gnb_id] = {
                    'index': latest['index'],
                    'position': (latest['x'], latest['y'], latest['z']),
                    'connected_ues': latest['connected_ues'],
                    'num_connected': latest['num_connected'],
                    'total_records': len(records)
                }
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'simulation_time': {
                'start': self.start_time,
                'current': self.grid.last_update_time,
                'elapsed': elapsed_time
            },
            'ues': {
                'count': num_ues,
                'total_measurements': total_measurements,
                'avg_measurements_per_ue': total_measurements / num_ues if num_ues > 0 else 0
            },
            'gnbs': gnb_info,
            'coverage': stats,
            'qos': qos
        }
        
        return report
    
    def print_summary(self):
        """Imprime un resumen formateado en consola"""
        report = self.get_summary_report()
        
        print("\n" + "="*60)
        print("   COVERAGE ANALYSIS REPORT")
        print("="*60)
        
        if report['simulation_time']['elapsed']:
            print(f"Simulation Time: {report['simulation_time']['elapsed']:.2f} s")
        
        print(f"Active UEs: {report['ues']['count']}")
        print(f"Total Measurements: {report['ues']['total_measurements']}")
        
        # Información de gNodeBs
        if report['gnbs']:
            print("-"*60)
            print("gNodeB Status:")
            for gnb_id, info in report['gnbs'].items():
                print(f"  gNodeB[{info['index']}] (macNodeId={gnb_id}):")
                print(f"    Position: ({info['position'][0]:.1f}, {info['position'][1]:.1f}, {info['position'][2]:.1f})")
                print(f"    Connected UEs: {info['num_connected']} {info['connected_ues']}")
        
        print("-"*60)
        print(f"COVERAGE PERCENTAGE (of total area): {report['coverage']['coverage_percentage']:.2f}%")
        print(f"  Covered cells: {report['coverage']['covered_cells']} / {report['coverage']['total_cells']}")
        print(f"  Measured cells: {report['coverage']['measured_cells']} ({report['coverage']['measurement_percentage']:.1f}%)")
        print(f"  Avg SINR (covered): {report['coverage']['avg_sinr_covered']:.2f} dB")
        print("-"*60)
        print("QoS Distribution (of measured cells):")
        for level, data in report['qos'].items():
            print(f"  {level:15s}: {data['percentage']:6.2f}% ({data['cells']} cells)")
        print("-"*60)
        print("gNodeB Coverage Distribution (of measured cells):")
        for gnb_id, data in report['coverage']['gnb_distribution'].items():
            print(f"  gNodeB[{gnb_id-1}]: {data['percentage']:6.2f}% ({data['cells']} cells)")
        print("="*60 + "\n")
    
    def save_report(self, filename=None):
        """Guarda el reporte en formato JSON"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"coverage_report_{timestamp}.json"
        
        Path(RESULTS_DIR).mkdir(exist_ok=True)
        filepath = Path(RESULTS_DIR) / filename
        
        report = self.get_summary_report()
        
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"[CoverageAnalyzer] Report saved to {filepath}")
        
        return filepath

# ================= VISUALIZACIÓN =================
def plot_coverage_grid(coverage_grid, title="Coverage Map", save_path=None):
    """
    Genera mapa de cobertura binario con FONDO GRIS para celdas sin mediciones
    ORIGEN: Esquina superior izquierda
    """
    fig, ax = plt.subplots(figsize=(12, 10))
    
    display_map = np.full((coverage_grid.grid_rows, coverage_grid.grid_cols), -1)
    
    measured_mask = coverage_grid.measurement_count > 0
    display_map[measured_mask & (coverage_grid.coverage_map == 1)] = 1  # Verde
    display_map[measured_mask & (coverage_grid.coverage_map == 0)] = 0  # Rojo
    
    cmap = ListedColormap(['lightgray', 'red', 'lightgreen'])
    bounds = [-1.5, -0.5, 0.5, 1.5]
    norm = plt.cm.colors.BoundaryNorm(bounds, cmap.N)
    
    im = ax.imshow(display_map, cmap=cmap, norm=norm,
                   origin='upper',
                   extent=[0, AREA_SIZE_X, AREA_SIZE_Y, 0],
                   alpha=0.8)
    
    cbar = plt.colorbar(im, ax=ax, ticks=[-1, 0, 1])
    cbar.ax.set_yticklabels(['Sin mediciones', 'Sin Cobertura', 'Con Cobertura'])
    
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.set_xlabel('X (m)', fontsize=12)
    ax.set_ylabel('Y (m)', fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')
    
    stats = coverage_grid.get_coverage_statistics()
    textstr = f"Cobertura: {stats['coverage_percentage']:.1f}%\n"
    textstr += f"Celdas cubiertas: {stats['covered_cells']}/{stats['total_cells']}\n"
    textstr += f"SINR promedio: {stats['avg_sinr_covered']:.1f} dB"
    
    props = dict(boxstyle='round', facecolor='wheat', alpha=0.9)
    ax.text(0.02, 0.98, textstr, transform=ax.transAxes, fontsize=11,
            verticalalignment='top', bbox=props)
    
    plt.tight_layout()
    
    if save_path:
        Path(PLOTS_DIR).mkdir(exist_ok=True)
        full_path = Path(PLOTS_DIR) / save_path
        plt.savefig(full_path, dpi=300, bbox_inches='tight')
        print(f"[Visualization] Saved to {full_path}")
    
    plt.show(block=False)
    plt.pause(0.1)


def plot_sinr_heatmap(coverage_grid, title="SINR Heatmap", save_path=None):
    """
    Genera mapa de calor de SINR
    ORIGEN: Esquina superior izquierda (consistente con plot_coverage_grid)
    """
    fig, ax = plt.subplots(figsize=(12, 10))
    
    # Reemplazar -999 con NaN para mejor visualización
    sinr_map_clean = np.where(coverage_grid.sinr_map == -999, 
                               np.nan, coverage_grid.sinr_map)
    
    im = ax.imshow(sinr_map_clean, cmap='RdYlGn', 
                   origin='upper',
                   extent=[0, AREA_SIZE_X, AREA_SIZE_Y, 0],
                   vmin=-20, vmax=30)
    
    cbar = plt.colorbar(im, ax=ax, label='SINR (dB)')
    
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.set_xlabel('X (m)', fontsize=12)
    ax.set_ylabel('Y (m)', fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')
    
    plt.tight_layout()
    
    if save_path:
        Path(PLOTS_DIR).mkdir(exist_ok=True)
        full_path = Path(PLOTS_DIR) / save_path
        plt.savefig(full_path, dpi=300, bbox_inches='tight')
        print(f"[Visualization] Saved to {full_path}")
    
    plt.show(block=False)
    plt.pause(0.1)

# ================= XML INDENT =================

def indent_xml(elem, level=0):
    """Añade saltos de línea e indentación al XML"""
    i = "\n" + level * "    "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "    "
        for child in elem:
            indent_xml(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

# ================= ROUTE MANAGER =================

class RouteManager:
    def __init__(self, xml_path):
        self.xml_path = Path(xml_path)

        if not self.xml_path.exists():
            print(f"ERROR: No se encuentra el XML en {self.xml_path}")
            sys.exit(1)

        self.tree = ET.parse(self.xml_path)
        self.root = self.tree.getroot()

    def _find_node(self, node_name):
        return self.root.find(node_name)

    def clear_route(self, node_name):
        node = self._find_node(node_name)
        if node is None:
            print(f"[RouteManager] Nodo '{node_name}' no encontrado en el XML")
            return False

        node.clear()
        print(f"[RouteManager] Ruta anterior eliminada para {node_name}")
        return True

    def generate_route_to(self, node_name, target_x, target_y):
        """Genera una ruta TurtleMobility hacia (target_x, target_y)"""
        node = self._find_node(node_name)
        if node is None:
            print(f"[RouteManager] Nodo '{node_name}' no encontrado")
            return False

        # Posición inicial conocida
        ET.SubElement(node, "set", {
            "x": "1900",
            "y": "1800",
            "speed": "10",
            "angle": "225"
        })

        ET.SubElement(node, "forward", {"d": "990"})
        ET.SubElement(node, "wait", {"t": "2"})

        ET.SubElement(node, "turn", {"angle": "270"})
        ET.SubElement(node, "forward", {"d": "200"})
        ET.SubElement(node, "wait", {"t": "1"})

        # Posición final exacta
        ET.SubElement(node, "set", {
            "x": str(target_x),
            "y": str(target_y),
        })

        print(f"[RouteManager] Ruta generada hacia ({target_x}, {target_y})")
        return True

    def save_xml(self):
        indent_xml(self.root)
        self.tree.write(self.xml_path, encoding="UTF-8", xml_declaration=True)
        print(f"[RouteManager] XML guardado correctamente (formateado)")

# ================= SIGNAL HANDLER =================

def cerrar_servidor(sig=None, frame=None):
    global conn, server_running, coverage_analyzer
    
    print("\n[Servidor] Cerrando servidor...")
    server_running = False
    
    if ENABLE_FINAL_REPORT and coverage_analyzer:
        print("\n" + "="*60)
        print("GENERANDO REPORTE FINAL DE COBERTURA")
        print("="*60)
        
        # Mostrar resumen final
        coverage_analyzer.print_summary()
        
        # Guardar datos
        coverage_analyzer.save_report()
        coverage_analyzer.grid.save_to_file('final_coverage_grid.json')
        
        # Generar visualizaciones finales
        print("\n[Servidor] Generando visualizaciones...")
        plot_coverage_grid(coverage_analyzer.grid, 
                          "Mapa de Cobertura Final", 
                          "coverage_map_final.png")
        plot_sinr_heatmap(coverage_analyzer.grid, 
                         "Mapa SINR Final", 
                         "sinr_heatmap_final.png")
        print("\n[Servidor] Visualizaciones guardadas en:", PLOTS_DIR)
        
        # Mantener gráficos abiertos
        input("\nPresiona Enter para cerrar las visualizaciones y salir...")
        plt.close('all')
    
    if conn:
        try:
            conn.sendall(b"SERVER_CLOSED")
            conn.close()
        except Exception:
            pass
    
    sys.exit(0)

signal.signal(signal.SIGINT, cerrar_servidor)

# ================= MESSAGE PROCESSING =================

def process_position_message(route_mgr, analyzer, message):
    """Procesa mensajes de posición de UEs"""
    global route_already_modified

    try:
        # Procesar mensaje para análisis de cobertura
        if analyzer.process_ue_message(message):
            pass
        
        # Lógica original de modificación de ruta
        data = None
        if message.strip().startswith('{'):
            data = json.loads(message)
            sinr = data.get("network", {}).get("sinr")
        else:
            parts = message.strip().split(',')
            if parts[0] == "POS" and len(parts) >= 7:
                sinr = float(parts[5])
            else:
                return {"status": "ignored"}
        
        if sinr is None:
            return {"status": "ignored", "message": "SINR no presente"}

        print(f"[Servidor] SINR recibido: {sinr:.2f} dB")

        # Ruta ya modificada → solo logging
        if route_already_modified:
            return {"status": "ok", "message": "Ruta ya fijada"}

        # Primera caída por debajo del umbral
        if sinr < QOS_LEVELS['Excellent']:
            print(f"⚠️  SINR BAJO DETECTADO (<{QOS_LEVELS['Excellent']} dB)")
            print("📍 Modificando ruta del gNodeB (acción única)")

            if route_mgr.clear_route("gnodeb1"):
                route_mgr.generate_route_to("gnodeb1", 1200, 1200)
                route_mgr.save_xml()
                route_already_modified = True

                return {
                    "status": "success",
                    "message": "Ruta modificada (solo una vez)"
                }

        return {"status": "ok", "message": "SINR aceptable"}

    except json.JSONDecodeError:
        return {"status": "error", "message": "JSON inválido"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def process_coverage_message(route_mgr, analyzer, message):
    """Procesa mensajes de cobertura de los gNodeBs"""
    try:
        if analyzer.process_coverage_message(message):
            return {"status": "ok", "message": "Coverage data received"}
        else:
            return {"status": "ignored", "message": "Not a COVERAGE message"}
        
    except json.JSONDecodeError:
        return {"status": "error", "message": "JSON inválido"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ================= THREAD DE ANÁLISIS =================

last_analysis_time = 0
last_plot_time = 0

def analysis_thread(analyzer):
    """Thread que ejecuta análisis periódicos"""
    global last_analysis_time, last_plot_time, server_running
    
    while server_running:
        time.sleep(1.0)
        
        current_time = time.time()
        
        # Mostrar estadísticas en tiempo real
        if ENABLE_REALTIME_ANALYSIS and (current_time - last_analysis_time >= ANALYSIS_INTERVAL):
            if analyzer.grid.last_update_time is not None:
                analyzer.print_summary()
            last_analysis_time = current_time
        
        # Actualizar gráfico en tiempo real
        if ENABLE_REALTIME_PLOT and (current_time - last_plot_time >= PLOT_UPDATE_INTERVAL):
            if analyzer.grid.last_update_time is not None:
                print("\n[Servidor] Actualizando visualización en tiempo real...")
                plt.close('all')
                plot_coverage_grid(analyzer.grid, "Cobertura (Tiempo Real)")
            last_plot_time = current_time

# ================= SERVER LOOP =================

def main():
    global conn, addr, server_running, coverage_analyzer

    # Crear directorios
    Path(RESULTS_DIR).mkdir(exist_ok=True)
    Path(PLOTS_DIR).mkdir(exist_ok=True)

    route_mgr = RouteManager(MOBILITY_XML)
    coverage_analyzer = CoverageAnalyzer()

    # Iniciar thread de análisis
    analysis_thread_obj = threading.Thread(
        target=analysis_thread, 
        args=(coverage_analyzer,), 
        daemon=True
    )
    analysis_thread_obj.start()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen(1)

        print("="*60)
        print(f"[Servidor] Escuchando en {HOST}:{PORT}")
        print(f"[Servidor] XML movilidad: {MOBILITY_XML}")
        print(f"[Servidor] Análisis en tiempo real: {ENABLE_REALTIME_ANALYSIS}")
        print(f"[Servidor] Gráficos en tiempo real: {ENABLE_REALTIME_PLOT}")
        print("="*60)

        while server_running:
            conn, addr = s.accept()
            print(f"[Servidor] Conexión desde {addr}")

            with conn:
                while server_running:
                    data = conn.recv(4096)
                    if not data:
                        print("[Servidor] Cliente desconectado")
                        break

                    msg = data.decode("utf-8", errors="replace").strip()
                    
                    # Detectar tipo de mensaje y procesar
                    if msg.startswith("{"):
                        try:
                            data_json = json.loads(msg)
                            msg_type = data_json.get("type")
                            
                            if msg_type == "POS":
                                response = process_position_message(route_mgr, coverage_analyzer, msg)
                                conn.sendall(json.dumps(response).encode("utf-8"))
                            elif msg_type == "COVERAGE":
                                response = process_coverage_message(route_mgr, coverage_analyzer, msg)
                                conn.sendall(json.dumps(response).encode("utf-8"))
                            else:
                                conn.sendall(b"ACK")
                        except json.JSONDecodeError:
                            conn.sendall(b"ACK")
                    elif msg.startswith("POS"):
                        response = process_position_message(route_mgr, coverage_analyzer, msg)
                        conn.sendall(json.dumps(response).encode("utf-8"))
                    else:
                        conn.sendall(b"ACK")

if __name__ == "__main__":
    coverage_analyzer = None
    main()