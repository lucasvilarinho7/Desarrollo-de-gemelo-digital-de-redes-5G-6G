import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
import matplotlib.pyplot as plt
from shapely.ops import unary_union

# Cargar shapefile y filtrar

# gdf_esp = gpd.read_file("gadm41_ESP_shp/gadm41_ESP_4.shp") # Descargar de la web oficial de GADM
# gdf_madrid_poly = gdf_esp[gdf_esp["NAME_4"] == "Madrid"] # Filtrar solo el área de la Comunidad de Madrid

gdf_mad = gpd.read_file("./Distritos/distritos.shp") # Filtrar por barrio o distrito de Madrid

# Reproyectamos
gdf_mad = gdf_mad.to_crs(epsg=4326)

gdf_distrito_poly = gdf_mad[gdf_mad["NOMDIS"] == "Chamberí"] # Filtrar solo el área de un barrio o distrito




# Cargar CSV con estaciones 

df_madrid = pd.read_csv("NR_stations_Spain.csv")  


# Crear geometría de puntos

geometry = [Point(xy) for xy in zip(df_madrid['lon'], df_madrid['lat'])]
""" Código de identificación para el sistema de coordenadas geográficas WGS84, 
que utiliza latitud y longitud para ubicar puntos en la Tierra sobre un elipsoide 3D """
gdf_stations = gpd.GeoDataFrame(df_madrid, geometry=geometry, crs="EPSG:4326") 


# Filtrar estaciones dentro de la Comunidad de Madrid

distrito_poly = gdf_distrito_poly.geometry.union_all()
gdf_stations_inside = gdf_stations[gdf_stations.within(distrito_poly)]
gdf_stations_inside_filtrada = gdf_stations_inside.drop(columns=['geometry'], axis=1)
gdf_stations_inside_filtrada.to_csv("NR_stations_chamberí.csv", index=False) # Escribir el nuevo CSV con las estaciones filtradas

# Reproyectar a proyección métrica (UTM 30N)

gdf_stations_inside = gdf_stations_inside.to_crs(epsg=25830)
gdf_distrito_poly = gdf_distrito_poly.to_crs(epsg=25830)

# Crear buffers con el radio de cobertura

gdf_stations_inside['buffer'] = gdf_stations_inside.geometry.buffer(gdf_stations_inside['range'])
gdf_coverage = gpd.GeoDataFrame(gdf_stations_inside.drop(columns='geometry'), geometry=gdf_stations_inside['buffer'], crs=gdf_stations_inside.crs)

# # Calcular estadísticas de cobertura
# # Unión de todos los buffers (área total cubierta)
# total_union = unary_union(gdf_stations_inside['buffer'])

# # Suma de áreas individuales
# individual_sum = gdf_stations_inside['buffer'].area.sum()

# # Área total cubierta sin solapamientos
# area_covered = total_union.area

# # Área solapada
# overlapping_area = individual_sum - area_covered
# overlapping_percentage = (overlapping_area / individual_sum) * 100

# # Área total de la Comunidad de Madrid
# area_madrid = gdf_madrid_poly.geometry.area.sum()

# # Área sin cobertura
# area_without_coverage = area_madrid - area_covered
# porcentaje_sin_cobertura = (area_without_coverage / area_madrid) * 100

# print(f"Área total de la Comunidad de Madrid: {area_madrid/1e6:.2f} km²")
# print(f"Área cubierta por estaciones: {area_covered/1e6:.2f} km² ({100 - porcentaje_sin_cobertura:.2f} %)")
# print(f"Área sin cobertura: {area_without_coverage/1e6:.2f} km² ({porcentaje_sin_cobertura:.2f} %)")
# print(f"Área solapada: {overlapping_area/1e6:.2f} km² ({overlapping_percentage:.2f} %)")

# Crear etiquetas cortas
# Mapear cada valor 'cell' a una etiqueta corta tipo E001, E002, ...
# mapping_labels = {cell: f"E{idx+1:03d}" for idx, cell in enumerate(gdf_stations_inside["cell"].unique())}
# gdf_stations_inside["label"] = gdf_stations_inside["cell"].map(mapping_labels)

# Graficar
fig, ax = plt.subplots(figsize=(12, 12))

# Polígono del distrito
gdf_distrito_poly.plot(ax=ax, color='white', edgecolor='black')

# Círculos de cobertura
gdf_coverage.plot(ax=ax, color='blue', alpha=0.2, edgecolor='blue')

# Etiquetas cortas
# for x, y, label in zip(gdf_stations_inside.geometry.x, gdf_stations_inside.geometry.y, gdf_stations_inside["label"]):
#     ax.text(x, y, label, fontsize=6, ha='right', color='darkred')

# Estaciones
gdf_stations_inside.plot(ax=ax, color='red', markersize=8)

ax.set_title("Cobertura Estaciones NR - Distrito", fontsize=14)
ax.set_axis_off()
plt.show()
