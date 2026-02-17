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
from matplotlib.patches import Patch
from datetime import datetime
from collections import defaultdict

# ================= CONFIGURACIÓN GLOBAL =================

# --- Socket TCP ---
HOST = "0.0.0.0"
PORT = 50000

# --- Archivos ---
MOBILITY_XML = "../../simu5g-wk/GNBrectilineo/simulations/mobility_routes.xml"
RESULTS_DIR = "./coverage_results"
PLOTS_DIR = "./coverage_plots"

# --- Área de simulación (debe coincidir con omnetpp.ini) ---
AREA_SIZE_X = 2000  # metros
AREA_SIZE_Y = 2000  # metros
GRID_CELL_SIZE = 50  # metros (celdas de 50x50m)

# --- Umbrales de cobertura ---
SINR_THRESHOLD_COVERAGE = 20  # dB

# Niveles de QoS según SINR
QOS_LEVELS = {
    'Excellent': 20,
    'Good': 13,
    'Fair': 0,
    'Poor': -10,
    'No Service': -999
}

# --- Análisis ---
ENABLE_REALTIME_ANALYSIS = True
ANALYSIS_INTERVAL = 10.0

ENABLE_REALTIME_PLOT = False
PLOT_UPDATE_INTERVAL = 10.0

ENABLE_FINAL_REPORT = True

# ================= ESTADO GLOBAL =================

route_already_modified = False
conn = None
addr = None
server_running = True

# ================= TIMESTAMP DE SESIÓN =================

SESSION_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

# ================= CLASE: GRID DE COBERTURA =================

class CoverageGrid:
    def __init__(self, area_size_x=AREA_SIZE_X, area_size_y=AREA_SIZE_Y,
                 cell_size=GRID_CELL_SIZE):
        self.area_size_x = area_size_x
        self.area_size_y = area_size_y
        self.cell_size = cell_size

        self.grid_cols = int(np.ceil(area_size_x / cell_size))
        self.grid_rows = int(np.ceil(area_size_y / cell_size))

        self.coverage_map = np.zeros((self.grid_rows, self.grid_cols), dtype=int)
        self.sinr_map = np.full((self.grid_rows, self.grid_cols), -999.0)
        self.cell_id_map = np.full((self.grid_rows, self.grid_cols), -1, dtype=int)
        self.measurement_count = np.zeros((self.grid_rows, self.grid_cols), dtype=int)
        self.last_update_time = None

        print(f"[CoverageGrid] Initialized: {self.grid_rows}x{self.grid_cols} cells "
              f"({self.grid_rows * self.grid_cols} total)")

    def position_to_grid(self, x, y):
        col = int(x / self.cell_size)
        row = int(y / self.cell_size)
        col = max(0, min(col, self.grid_cols - 1))
        row = max(0, min(row, self.grid_rows - 1))
        return row, col

    def update_from_ue_measurement(self, x, y, sinr, cell_id, timestamp):
        row, col = self.position_to_grid(x, y)

        if sinr >= SINR_THRESHOLD_COVERAGE:
            self.coverage_map[row, col] = 1
        else:
            self.coverage_map[row, col] = 0

        if self.measurement_count[row, col] == 0:
            self.sinr_map[row, col] = sinr
        else:
            alpha = 0.3
            self.sinr_map[row, col] = (alpha * sinr +
                                       (1 - alpha) * self.sinr_map[row, col])

        self.cell_id_map[row, col] = cell_id
        self.measurement_count[row, col] += 1
        self.last_update_time = timestamp

    def get_coverage_percentage(self):
        total_cells = self.grid_rows * self.grid_cols
        covered_cells = np.sum(self.coverage_map)
        return (covered_cells / total_cells) * 100

    def get_coverage_statistics(self):
        total_cells = self.grid_rows * self.grid_cols
        covered_cells = np.sum(self.coverage_map)
        uncovered_cells = total_cells - covered_cells
        measured_cells = np.sum(self.measurement_count > 0)
        unmeasured_cells = total_cells - measured_cells

        covered_sinr_values = self.sinr_map[self.coverage_map == 1]
        if len(covered_sinr_values) > 0:
            avg_sinr_covered = np.mean(covered_sinr_values)
            min_sinr_covered = np.min(covered_sinr_values)
            max_sinr_covered = np.max(covered_sinr_values)
        else:
            avg_sinr_covered = min_sinr_covered = max_sinr_covered = -999

        gnb_distribution = {}
        for gnb_id in np.unique(self.cell_id_map):
            if gnb_id >= 0:
                cells_served = np.sum(self.cell_id_map == gnb_id)
                gnb_distribution[int(gnb_id)] = {
                    'cells': int(cells_served),
                    'percentage': (cells_served / measured_cells * 100) if measured_cells > 0 else 0
                }

        return {
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

    def get_qos_distribution(self):
        measured_mask = self.measurement_count > 0
        total_measured_cells = np.sum(measured_mask)

        if total_measured_cells == 0:
            return {level: {'cells': 0, 'percentage': 0.0}
                    for level in QOS_LEVELS.keys()}

        measured_sinr = self.sinr_map[measured_mask]

        distribution = {}
        excellent_count = np.sum(measured_sinr >= 20)
        distribution['Excellent'] = {
            'cells': int(excellent_count),
            'percentage': (excellent_count / total_measured_cells) * 100
        }
        good_count = np.sum((measured_sinr >= 13) & (measured_sinr < 20))
        distribution['Good'] = {
            'cells': int(good_count),
            'percentage': (good_count / total_measured_cells) * 100
        }
        fair_count = np.sum((measured_sinr >= 0) & (measured_sinr < 13))
        distribution['Fair'] = {
            'cells': int(fair_count),
            'percentage': (fair_count / total_measured_cells) * 100
        }
        poor_count = np.sum((measured_sinr >= -10) & (measured_sinr < 0))
        distribution['Poor'] = {
            'cells': int(poor_count),
            'percentage': (poor_count / total_measured_cells) * 100
        }
        no_service_count = np.sum(measured_sinr < -10)
        distribution['No Service'] = {
            'cells': int(no_service_count),
            'percentage': (no_service_count / total_measured_cells) * 100
        }

        return distribution


# ================= CLASE: DETECTOR DE COVERAGE HOLES =================

class CoverageHoleDetector:
    """
    Detecta y caracteriza zonas sin cobertura (coverage holes).

    Tipos de holes:
      - measured:  Celda medida con SINR por debajo del umbral
      - inferred:  Celda no medida rodeada de celdas con mala cobertura

    Agrupa celdas en regiones con DBSCAN y las prioriza por severidad.
    """

    SEVERE_THRESHOLD = -10
    POOR_THRESHOLD = 0
    FAIR_THRESHOLD = 13
    COVERAGE_THRESHOLD = 20

    DBSCAN_EPS_CELLS = 2
    DBSCAN_MIN_SAMPLES = 2

    def __init__(self, coverage_grid):
        self.grid = coverage_grid
        self.holes = []
        self.hole_cells = []
        self.last_detection_time = None

    def detect(self):
        self.hole_cells = []
        self.holes = []

        self._identify_hole_cells()

        if not self.hole_cells:
            self.last_detection_time = self.grid.last_update_time
            return self.holes

        self._cluster_holes()
        self._characterize_regions()

        self.last_detection_time = self.grid.last_update_time
        return self.holes

    def _identify_hole_cells(self):
        grid = self.grid

        for row in range(grid.grid_rows):
            for col in range(grid.grid_cols):
                measured = grid.measurement_count[row, col] > 0
                sinr = grid.sinr_map[row, col]

                if measured and sinr < self.COVERAGE_THRESHOLD:
                    severity = self._classify_severity(sinr)
                    self.hole_cells.append({
                        'row': row, 'col': col,
                        'x': (col + 0.5) * grid.cell_size,
                        'y': (row + 0.5) * grid.cell_size,
                        'sinr': float(sinr),
                        'severity': severity,
                        'type': 'measured',
                        'measurements': int(grid.measurement_count[row, col])
                    })

                elif not measured:
                    neighbors_measured = 0
                    neighbors_poor = 0

                    for dr in [-1, 0, 1]:
                        for dc in [-1, 0, 1]:
                            if dr == 0 and dc == 0:
                                continue
                            nr, nc = row + dr, col + dc
                            if 0 <= nr < grid.grid_rows and 0 <= nc < grid.grid_cols:
                                if grid.measurement_count[nr, nc] > 0:
                                    neighbors_measured += 1
                                    if grid.sinr_map[nr, nc] < self.COVERAGE_THRESHOLD:
                                        neighbors_poor += 1

                    if neighbors_measured >= 3 and neighbors_poor >= 2:
                        avg_sinr = self._avg_neighbor_sinr(row, col)
                        self.hole_cells.append({
                            'row': row, 'col': col,
                            'x': (col + 0.5) * grid.cell_size,
                            'y': (row + 0.5) * grid.cell_size,
                            'sinr': float(avg_sinr),
                            'severity': self._classify_severity(avg_sinr),
                            'type': 'inferred',
                            'measurements': 0
                        })

    def _avg_neighbor_sinr(self, row, col):
        grid = self.grid
        sinr_values = []
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                if dr == 0 and dc == 0:
                    continue
                nr, nc = row + dr, col + dc
                if 0 <= nr < grid.grid_rows and 0 <= nc < grid.grid_cols:
                    if grid.measurement_count[nr, nc] > 0:
                        sinr_values.append(grid.sinr_map[nr, nc])
        return np.mean(sinr_values) if sinr_values else -999.0

    def _classify_severity(self, sinr):
        if sinr < self.SEVERE_THRESHOLD:
            return 'critical'
        elif sinr < self.POOR_THRESHOLD:
            return 'severe'
        elif sinr < self.FAIR_THRESHOLD:
            return 'moderate'
        else:
            return 'mild'

    def _cluster_holes(self):
        if len(self.hole_cells) < self.DBSCAN_MIN_SAMPLES:
            for i, cell in enumerate(self.hole_cells):
                cell['cluster_id'] = i
            return

        try:
            from sklearn.cluster import DBSCAN
            coords = np.array([[c['row'], c['col']] for c in self.hole_cells])
            clustering = DBSCAN(
                eps=self.DBSCAN_EPS_CELLS,
                min_samples=self.DBSCAN_MIN_SAMPLES
            ).fit(coords)
            for i, label in enumerate(clustering.labels_):
                self.hole_cells[i]['cluster_id'] = int(label)
        except ImportError:
            print("[CoverageHoleDetector] sklearn no disponible, usando clustering simple")
            self._cluster_holes_simple()

    def _cluster_holes_simple(self):
        visited = set()
        cluster_id = 0

        for i, cell in enumerate(self.hole_cells):
            if i in visited:
                continue

            queue = [i]
            visited.add(i)
            cluster_members = [i]

            while queue:
                current = queue.pop(0)
                cr = self.hole_cells[current]['row']
                cc = self.hole_cells[current]['col']

                for j, other in enumerate(self.hole_cells):
                    if j in visited:
                        continue
                    dist = abs(other['row'] - cr) + abs(other['col'] - cc)
                    if dist <= self.DBSCAN_EPS_CELLS:
                        visited.add(j)
                        queue.append(j)
                        cluster_members.append(j)

            cid = cluster_id if len(cluster_members) >= self.DBSCAN_MIN_SAMPLES else -1
            for idx in cluster_members:
                self.hole_cells[idx]['cluster_id'] = cid

            if len(cluster_members) >= self.DBSCAN_MIN_SAMPLES:
                cluster_id += 1

    def _characterize_regions(self):
        self.holes = []

        clusters = defaultdict(list)
        for cell in self.hole_cells:
            clusters[cell['cluster_id']].append(cell)

        for cluster_id, cells in sorted(clusters.items()):
            if cluster_id == -1:
                for cell in cells:
                    self.holes.append(self._make_hole_entry(
                        hole_id=f"isolated_{cell['row']}_{cell['col']}",
                        hole_type='isolated',
                        cells=[cell]
                    ))
                continue

            self.holes.append(self._make_hole_entry(
                hole_id=f"region_{cluster_id}",
                hole_type='cluster',
                cells=cells
            ))

        self.holes.sort(key=lambda h: (-h['severity_score'], -h['area_m2']))

    def _make_hole_entry(self, hole_id, hole_type, cells):
        xs = [c['x'] for c in cells]
        ys = [c['y'] for c in cells]
        sinrs = [c['sinr'] for c in cells if c['sinr'] > -999]
        severities = [c['severity'] for c in cells]
        measured_count = sum(1 for c in cells if c['type'] == 'measured')
        cs = self.grid.cell_size

        worst = self._worst_severity(severities)

        return {
            'id': hole_id,
            'type': hole_type,
            'center': {'x': float(np.mean(xs)), 'y': float(np.mean(ys))},
            'area_m2': float(len(cells) * cs * cs),
            'num_cells': len(cells),
            'avg_sinr': float(np.mean(sinrs)) if sinrs else -999.0,
            'min_sinr': float(np.min(sinrs)) if sinrs else -999.0,
            'severity': worst,
            'severity_score': self._severity_score(worst),
            'measured_ratio': measured_count / len(cells) if cells else 0,
            'bounding_box': {
                'x_min': float(min(xs) - cs / 2),
                'x_max': float(max(xs) + cs / 2),
                'y_min': float(min(ys) - cs / 2),
                'y_max': float(max(ys) + cs / 2)
            }
        }

    def _severity_score(self, severity):
        return {'critical': 4, 'severe': 3, 'moderate': 2, 'mild': 1}.get(severity, 0)

    def _worst_severity(self, severities):
        for level in ['critical', 'severe', 'moderate', 'mild']:
            if level in severities:
                return level
        return 'mild'

    def get_summary(self):
        if not self.holes:
            return {
                'total_holes': 0,
                'total_cells_affected': 0,
                'total_area_m2': 0,
                'by_severity': {},
                'regions': [],
                'detection_time': self.last_detection_time
            }

        total_cells = sum(h['num_cells'] for h in self.holes)
        total_area = sum(h['area_m2'] for h in self.holes)

        by_severity = defaultdict(lambda: {'count': 0, 'cells': 0, 'area_m2': 0})
        for h in self.holes:
            s = h['severity']
            by_severity[s]['count'] += 1
            by_severity[s]['cells'] += h['num_cells']
            by_severity[s]['area_m2'] += h['area_m2']

        regions_summary = []
        for h in self.holes:
            regions_summary.append({
                'id': h['id'],
                'type': h['type'],
                'center': h['center'],
                'area_m2': h['area_m2'],
                'num_cells': h['num_cells'],
                'avg_sinr': h['avg_sinr'],
                'min_sinr': h['min_sinr'],
                'severity': h['severity'],
                'severity_score': h['severity_score'],
                'measured_ratio': h['measured_ratio'],
                'bounding_box': h['bounding_box']
            })

        return {
            'total_holes': len(self.holes),
            'total_cells_affected': total_cells,
            'total_area_m2': total_area,
            'by_severity': dict(by_severity),
            'regions': regions_summary,
            'detection_time': self.last_detection_time
        }

    def print_summary(self):
        summary = self.get_summary()

        print("\n" + "="*60)
        print("   🕳️  COVERAGE HOLE DETECTION")
        print("="*60)

        if summary['total_holes'] == 0:
            print("  ✅ No coverage holes detected")
            print("="*60 + "\n")
            return

        print(f"  Total regions : {summary['total_holes']}")
        print(f"  Cells affected: {summary['total_cells_affected']}")
        print(f"  Area affected : {summary['total_area_m2']:.0f} m²")

        print("-"*60)
        print("  By severity:")
        icons = {'critical': '🔴', 'severe': '🟠', 'moderate': '🟡', 'mild': '🟢'}
        for sev in ['critical', 'severe', 'moderate', 'mild']:
            if sev in summary['by_severity']:
                d = summary['by_severity'][sev]
                print(f"    {icons[sev]} {sev:10s}: {d['count']} regions, "
                      f"{d['cells']} cells, {d['area_m2']:.0f} m²")

        print("-"*60)
        print("  Top coverage holes (prioritized):")
        for i, r in enumerate(summary['regions'][:10]):
            icon = icons.get(r['severity'], '⚪')
            print(f"    {i+1}. {icon} [{r['severity']}] "
                  f"center=({r['center']['x']:.0f}, {r['center']['y']:.0f}) "
                  f"area={r['area_m2']:.0f}m² "
                  f"SINR={r['avg_sinr']:.1f}dB "
                  f"({r['num_cells']} cells)")

        print("="*60 + "\n")


# ================= CLASE: ANALIZADOR DE COBERTURA =================

class CoverageAnalyzer:
    def __init__(self):
        self.grid = CoverageGrid()
        self.ue_data = defaultdict(list)
        self.gnb_data = {}
        self.start_time = None
        self.hole_detector = CoverageHoleDetector(self.grid)

        print("[CoverageAnalyzer] Initialized")

    def process_ue_message(self, message):
        try:
            data = json.loads(message)
            if data.get("type") != "POS":
                return False

            ue_id = data.get("ue_id", -1)
            ue_index = data.get("ue_index", -1)
            timestamp = data.get("timestamp")
            position = data.get("position", {})
            network = data.get("network", {})

            x = position.get("x", 0)
            y = position.get("y", 0)
            z = position.get("z", 0)
            sinr = network.get("sinr", -999)
            master_id = network.get("master_id", -1)

            self.grid.update_from_ue_measurement(x, y, sinr, master_id, timestamp)

            self.ue_data[ue_id].append({
                'timestamp': timestamp, 'ue_index': ue_index,
                'x': x, 'y': y, 'z': z,
                'sinr': sinr, 'master_id': master_id
            })

            if self.start_time is None:
                self.start_time = timestamp
            return True

        except json.JSONDecodeError as e:
            print(f"[CoverageAnalyzer] JSON error UE: {e}")
            return False
        except Exception as e:
            print(f"[CoverageAnalyzer] Error UE: {e}")
            return False

    def process_coverage_message(self, message):
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

            print(f"\n[Servidor] 📡 COVERAGE from gNodeB[{gnb_index}] (id={gnb_id})")
            print(f"  Time: {timestamp:.2f}s | Pos: ({x:.1f}, {y:.1f}, {z:.1f})")
            print(f"  Connected UEs: {num_connected} {connected_ues if connected_ues else ''}")

            if gnb_id not in self.gnb_data:
                self.gnb_data[gnb_id] = []

            self.gnb_data[gnb_id].append({
                'timestamp': timestamp, 'index': gnb_index,
                'x': x, 'y': y, 'z': z,
                'connected_ues': connected_ues, 'num_connected': num_connected
            })
            return True

        except json.JSONDecodeError:
            print("[CoverageAnalyzer] JSON inválido COVERAGE")
            return False
        except Exception as e:
            print(f"[CoverageAnalyzer] Error COVERAGE: {e}")
            return False

    def detect_coverage_holes(self):
        return self.hole_detector.detect()

    def get_summary_report(self):
        stats = self.grid.get_coverage_statistics()
        qos = self.grid.get_qos_distribution()

        num_ues = len(self.ue_data)
        total_measurements = sum(len(m) for m in self.ue_data.values())

        elapsed_time = None
        if self.start_time and self.grid.last_update_time:
            elapsed_time = self.grid.last_update_time - self.start_time

        ue_info = {}
        for ue_id, records in self.ue_data.items():
            if records:
                latest = records[-1]
                sinr_values = [r['sinr'] for r in records if r['sinr'] > -999]
                ue_info[ue_id] = {
                    'ue_index': latest['ue_index'],
                    'position': (latest['x'], latest['y'], latest['z']),
                    'current_sinr': latest['sinr'],
                    'avg_sinr': sum(sinr_values) / len(sinr_values) if sinr_values else -999,
                    'master_id': latest['master_id'],
                    'total_measurements': len(records)
                }

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

        self.detect_coverage_holes()

        return {
            'timestamp': datetime.now().isoformat(),
            'session': SESSION_TIMESTAMP,
            'simulation_time': {
                'start': self.start_time,
                'current': self.grid.last_update_time,
                'elapsed': elapsed_time
            },
            'ues': {
                'count': num_ues,
                'total_measurements': total_measurements,
                'details': ue_info
            },
            'gnbs': gnb_info,
            'coverage': stats,
            'qos': qos,
            'coverage_holes': self.hole_detector.get_summary()
        }

    def print_summary(self):
        report = self.get_summary_report()

        print("\n" + "="*60)
        print("   COVERAGE ANALYSIS REPORT")
        print("="*60)

        if report['simulation_time']['elapsed']:
            print(f"Simulation Time: {report['simulation_time']['elapsed']:.2f} s")

        print("-"*60)
        print(f"Active UEs: {report['ues']['count']}  |  "
              f"Total Measurements: {report['ues']['total_measurements']}")
        if report['ues']['details']:
            for ue_id, info in report['ues']['details'].items():
                print(f"  UE[{info['ue_index']}] (id={ue_id}):")
                print(f"    Position : ({info['position'][0]:.1f}, {info['position'][1]:.1f}, {info['position'][2]:.1f})")
                print(f"    SINR     : {info['current_sinr']:.2f} dB (avg: {info['avg_sinr']:.2f} dB)")
                print(f"    Serving  : gNodeB macNodeId={info['master_id']}")
                print(f"    Samples  : {info['total_measurements']}")

        if report['gnbs']:
            print("-"*60)
            print("gNodeB Status:")
            for gnb_id, info in report['gnbs'].items():
                print(f"  gNodeB[{info['index']}] (macNodeId={gnb_id}):")
                print(f"    Position: ({info['position'][0]:.1f}, {info['position'][1]:.1f}, {info['position'][2]:.1f})")
                print(f"    Connected UEs: {info['num_connected']} {info['connected_ues']}")

        print("-"*60)
        print(f"COVERAGE (total area): {report['coverage']['coverage_percentage']:.2f}%")
        print(f"  Covered cells: {report['coverage']['covered_cells']} / {report['coverage']['total_cells']}")
        print(f"  Measured cells: {report['coverage']['measured_cells']} ({report['coverage']['measurement_percentage']:.1f}%)")
        print(f"  Avg SINR (covered): {report['coverage']['avg_sinr_covered']:.2f} dB")
        print("-"*60)
        print("QoS Distribution (measured cells):")
        for level, data in report['qos'].items():
            bar = "█" * int(data['percentage'] / 5)
            print(f"  {level:15s}: {data['percentage']:6.2f}% ({data['cells']:3d} cells) {bar}")
        print("-"*60)
        print("gNodeB Cell Distribution (measured cells):")
        for gnb_id, data in report['coverage']['gnb_distribution'].items():
            print(f"  gNodeB macNodeId={gnb_id}: {data['percentage']:6.2f}% ({data['cells']} cells)")

        # Coverage Holes
        self.hole_detector.print_summary()

    def save_report(self):
        filename = f"coverage_report_{SESSION_TIMESTAMP}.json"
        Path(RESULTS_DIR).mkdir(exist_ok=True)
        filepath = Path(RESULTS_DIR) / filename
        report = self.get_summary_report()

        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        print(f"[CoverageAnalyzer] Report saved to {filepath}")
        return filepath


# ================= VISUALIZACIÓN =================

def plot_coverage_grid(coverage_grid, title="Coverage Map", save_path=None):
    fig, ax = plt.subplots(figsize=(12, 10))

    display_map = np.full((coverage_grid.grid_rows, coverage_grid.grid_cols), -1)
    measured_mask = coverage_grid.measurement_count > 0
    display_map[measured_mask & (coverage_grid.coverage_map == 1)] = 1
    display_map[measured_mask & (coverage_grid.coverage_map == 0)] = 0

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
    textstr = (f"Cobertura: {stats['coverage_percentage']:.1f}%\n"
               f"Celdas cubiertas: {stats['covered_cells']}/{stats['total_cells']}\n"
               f"SINR promedio: {stats['avg_sinr_covered']:.1f} dB")
    props = dict(boxstyle='round', facecolor='wheat', alpha=0.9)
    ax.text(0.02, 0.98, textstr, transform=ax.transAxes, fontsize=11,
            verticalalignment='top', bbox=props)

    plt.tight_layout()

    if save_path:
        Path(PLOTS_DIR).mkdir(exist_ok=True)
        plt.savefig(Path(PLOTS_DIR) / save_path, dpi=300, bbox_inches='tight')
        print(f"[Visualization] Saved to {PLOTS_DIR}/{save_path}")

    plt.show(block=False)
    plt.pause(0.1)


def plot_sinr_heatmap(coverage_grid, title="SINR Heatmap", save_path=None):
    fig, ax = plt.subplots(figsize=(12, 10))

    sinr_map_clean = np.where(coverage_grid.sinr_map == -999,
                               np.nan, coverage_grid.sinr_map)

    im = ax.imshow(sinr_map_clean, cmap='RdYlGn',
                   origin='upper',
                   extent=[0, AREA_SIZE_X, AREA_SIZE_Y, 0],
                   vmin=-20, vmax=30)

    plt.colorbar(im, ax=ax, label='SINR (dB)')

    ax.grid(True, alpha=0.3, linestyle='--')
    ax.set_xlabel('X (m)', fontsize=12)
    ax.set_ylabel('Y (m)', fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')

    plt.tight_layout()

    if save_path:
        Path(PLOTS_DIR).mkdir(exist_ok=True)
        plt.savefig(Path(PLOTS_DIR) / save_path, dpi=300, bbox_inches='tight')
        print(f"[Visualization] Saved to {PLOTS_DIR}/{save_path}")

    plt.show(block=False)
    plt.pause(0.1)


def plot_coverage_holes(coverage_grid, hole_detector, title="Coverage Holes",
                        save_path=None):
    fig, ax = plt.subplots(figsize=(14, 11))

    # Fondo: mapa SINR
    sinr_display = np.where(coverage_grid.sinr_map == -999,
                            np.nan, coverage_grid.sinr_map)

    im = ax.imshow(sinr_display, cmap='RdYlGn',
                   origin='upper',
                   extent=[0, coverage_grid.area_size_x,
                           coverage_grid.area_size_y, 0],
                   vmin=-20, vmax=30, alpha=0.6)

    plt.colorbar(im, ax=ax, label='SINR (dB)', shrink=0.8)

    # Colores por severidad
    severity_colors = {
        'critical': '#FF0000',
        'severe': '#FF6600',
        'moderate': '#FFCC00',
        'mild': '#99CC00'
    }

    for hole in hole_detector.holes:
        color = severity_colors.get(hole['severity'], '#888888')
        bb = hole['bounding_box']

        if hole['type'] == 'cluster':
            rect = plt.Rectangle(
                (bb['x_min'], bb['y_min']),
                bb['x_max'] - bb['x_min'],
                bb['y_max'] - bb['y_min'],
                linewidth=2, edgecolor=color,
                facecolor=color, alpha=0.25
            )
            ax.add_patch(rect)

            ax.plot(hole['center']['x'], hole['center']['y'],
                    'x', color=color, markersize=10, markeredgewidth=2)

            ax.annotate(
                f"{hole['severity']}\n{hole['area_m2']:.0f}m²\n{hole['avg_sinr']:.1f}dB",
                (hole['center']['x'], hole['center']['y']),
                fontsize=7, ha='center', va='bottom',
                color='white', fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.2', facecolor=color, alpha=0.8)
            )
        else:
            ax.plot(hole['center']['x'], hole['center']['y'],
                    's', color=color, markersize=6, alpha=0.7)

    # Leyenda
    legend_elements = [
        Patch(facecolor='#FF0000', alpha=0.5, label='Critical (SINR < -10 dB)'),
        Patch(facecolor='#FF6600', alpha=0.5, label='Severe (-10 ≤ SINR < 0 dB)'),
        Patch(facecolor='#FFCC00', alpha=0.5, label='Moderate (0 ≤ SINR < 13 dB)'),
        Patch(facecolor='#99CC00', alpha=0.5, label='Mild (13 ≤ SINR < 20 dB)'),
    ]
    ax.legend(handles=legend_elements, loc='lower right', fontsize=9)

    summary = hole_detector.get_summary()
    textstr = (f"Coverage Holes: {summary['total_holes']}\n"
               f"Cells affected: {summary['total_cells_affected']}\n"
               f"Area affected: {summary['total_area_m2']:.0f} m²")
    props = dict(boxstyle='round', facecolor='black', alpha=0.7)
    ax.text(0.02, 0.98, textstr, transform=ax.transAxes, fontsize=11,
            verticalalignment='top', color='white', bbox=props)

    ax.grid(True, alpha=0.2, linestyle='--')
    ax.set_xlabel('X (m)', fontsize=12)
    ax.set_ylabel('Y (m)', fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')

    plt.tight_layout()

    if save_path:
        Path(PLOTS_DIR).mkdir(exist_ok=True)
        plt.savefig(Path(PLOTS_DIR) / save_path, dpi=300, bbox_inches='tight')
        print(f"[Visualization] Saved to {PLOTS_DIR}/{save_path}")

    plt.show(block=False)
    plt.pause(0.1)


# ================= XML INDENT =================

def indent_xml(elem, level=0):
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
            print(f"[RouteManager] Nodo '{node_name}' no encontrado")
            return False
        node.clear()
        print(f"[RouteManager] Ruta eliminada para {node_name}")
        return True

    def generate_route_to(self, node_name, target_x, target_y):
        node = self._find_node(node_name)
        if node is None:
            print(f"[RouteManager] Nodo '{node_name}' no encontrado")
            return False
        ET.SubElement(node, "set", {"x": "1900", "y": "1800", "speed": "10", "angle": "225"})
        ET.SubElement(node, "forward", {"d": "990"})
        ET.SubElement(node, "wait", {"t": "2"})
        ET.SubElement(node, "turn", {"angle": "270"})
        ET.SubElement(node, "forward", {"d": "200"})
        ET.SubElement(node, "wait", {"t": "1"})
        ET.SubElement(node, "set", {"x": str(target_x), "y": str(target_y)})
        print(f"[RouteManager] Ruta generada hacia ({target_x}, {target_y})")
        return True

    def save_xml(self):
        indent_xml(self.root)
        self.tree.write(self.xml_path, encoding="UTF-8", xml_declaration=True)
        print(f"[RouteManager] XML guardado")


# ================= SIGNAL HANDLER =================

def cerrar_servidor(sig=None, frame=None):
    global conn, server_running, coverage_analyzer

    print("\n[Servidor] Cerrando servidor...")
    server_running = False

    if ENABLE_FINAL_REPORT and coverage_analyzer:
        print("\n" + "="*60)
        print("GENERANDO REPORTE FINAL")
        print("="*60)

        coverage_analyzer.detect_coverage_holes()
        coverage_analyzer.print_summary()
        coverage_analyzer.save_report()

        print("\n[Servidor] Generando visualizaciones...")
        plot_coverage_grid(coverage_analyzer.grid,
                          "Mapa de Cobertura Final",
                          f"coverage_map_{SESSION_TIMESTAMP}.png")
        plot_sinr_heatmap(coverage_analyzer.grid,
                         "Mapa SINR Final",
                         f"sinr_heatmap_{SESSION_TIMESTAMP}.png")
        plot_coverage_holes(coverage_analyzer.grid,
                           coverage_analyzer.hole_detector,
                           "Coverage Holes Detectados",
                           f"coverage_holes_{SESSION_TIMESTAMP}.png")

        print(f"\n[Servidor] Resultados en: {RESULTS_DIR} / {PLOTS_DIR}")
        print(f"[Servidor] Session: {SESSION_TIMESTAMP}")

        input("\nPresiona Enter para cerrar...")
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
    global route_already_modified

    try:
        analyzer.process_ue_message(message)

        data = json.loads(message)
        sinr = data.get("network", {}).get("sinr")
        ue_id = data.get("ue_id", "?")
        ue_index = data.get("ue_index", "?")

        if sinr is None:
            return {"status": "ignored", "message": "SINR no presente"}

        print(f"[Servidor] 📶 UE[{ue_index}] (id={ue_id}) SINR: {sinr:.2f} dB")

        if route_already_modified:
            return {"status": "ok", "message": "Ruta ya fijada"}

        if sinr < QOS_LEVELS['Excellent']:
            print(f"⚠️  SINR BAJO en UE[{ue_index}] (<{QOS_LEVELS['Excellent']} dB)")
            print("📍 Modificando ruta del gNodeB (acción única)")

            if route_mgr.clear_route("gnodeb1"):
                route_mgr.generate_route_to("gnodeb1", 1200, 1200)
                route_mgr.save_xml()
                route_already_modified = True
                return {"status": "success", "message": "Ruta modificada"}

        return {"status": "ok", "message": "SINR aceptable"}

    except json.JSONDecodeError:
        return {"status": "error", "message": "JSON inválido"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def process_coverage_message(route_mgr, analyzer, message):
    try:
        if analyzer.process_coverage_message(message):
            return {"status": "ok", "message": "Coverage data received"}
        else:
            return {"status": "ignored", "message": "Not a COVERAGE message"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ================= HELPER: SPLIT TCP STREAM =================

def split_tcp_messages(raw_data):
    messages = []
    remaining = raw_data.strip()

    while remaining:
        remaining = remaining.strip()
        if not remaining:
            break

        if remaining.startswith('{'):
            depth = 0
            for i, ch in enumerate(remaining):
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        messages.append(remaining[:i+1])
                        remaining = remaining[i+1:]
                        break
            else:
                messages.append(remaining)
                remaining = ""
        else:
            next_json = remaining.find('{')
            if next_json > 0:
                remaining = remaining[next_json:]
            else:
                break

    return messages


# ================= THREAD DE ANÁLISIS =================

last_analysis_time = 0
last_plot_time = 0

def analysis_thread(analyzer):
    global last_analysis_time, last_plot_time, server_running

    while server_running:
        time.sleep(1.0)
        current_time = time.time()

        if ENABLE_REALTIME_ANALYSIS and (current_time - last_analysis_time >= ANALYSIS_INTERVAL):
            if analyzer.grid.last_update_time is not None:
                analyzer.print_summary()
            last_analysis_time = current_time

        if ENABLE_REALTIME_PLOT and (current_time - last_plot_time >= PLOT_UPDATE_INTERVAL):
            if analyzer.grid.last_update_time is not None:
                plt.close('all')
                plot_coverage_grid(analyzer.grid, "Cobertura (Tiempo Real)")
            last_plot_time = current_time


# ================= SERVER LOOP =================

def main():
    global conn, addr, server_running, coverage_analyzer

    Path(RESULTS_DIR).mkdir(exist_ok=True)
    Path(PLOTS_DIR).mkdir(exist_ok=True)

    route_mgr = RouteManager(MOBILITY_XML)
    coverage_analyzer = CoverageAnalyzer()

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
        print(f"[Servidor] Session: {SESSION_TIMESTAMP}")
        print(f"[Servidor] XML movilidad: {MOBILITY_XML}")
        print(f"[Servidor] Formato: JSON (POS + COVERAGE)")
        print(f"[Servidor] Análisis en tiempo real: {ENABLE_REALTIME_ANALYSIS}")
        print(f"[Servidor] Detección de Coverage Holes: activada")
        print("="*60)

        while server_running:
            conn, addr = s.accept()
            print(f"[Servidor] Conexión desde {addr}")

            with conn:
                while server_running:
                    data = conn.recv(8192)
                    if not data:
                        print("[Servidor] Cliente desconectado")
                        break

                    raw = data.decode("utf-8", errors="replace").strip()
                    messages = split_tcp_messages(raw)

                    response = None
                    for msg in messages:
                        msg = msg.strip()
                        if not msg:
                            continue

                        try:
                            data_json = json.loads(msg)
                            msg_type = data_json.get("type")

                            if msg_type == "POS":
                                response = process_position_message(
                                    route_mgr, coverage_analyzer, msg)
                            elif msg_type == "COVERAGE":
                                response = process_coverage_message(
                                    route_mgr, coverage_analyzer, msg)
                            else:
                                print(f"[Servidor] Tipo desconocido: {msg_type}")
                                response = {"status": "ignored"}
                        except json.JSONDecodeError as e:
                            print(f"[Servidor] JSON inválido: {e}")
                            response = {"status": "error", "message": "Invalid JSON"}

                    if response:
                        try:
                            conn.sendall(json.dumps(response).encode("utf-8"))
                        except Exception as e:
                            print(f"[Servidor] Error enviando respuesta: {e}")
                    else:
                        conn.sendall(b"ACK")


if __name__ == "__main__":
    coverage_analyzer = None
    main()