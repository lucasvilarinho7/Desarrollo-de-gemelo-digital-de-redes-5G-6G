import pandas as pd

columns = [
    "radio", 
    "mcc",       
    "net",
    "area",           
    "cell",           
    "unit",           
    "lon",            
    "lat",            
    "range",          
    "samples",        
    "changeable",     
    "created",        
    "updated",        
    "averageSignal"   
]

df = pd.read_csv("OpenCelliD_Spain.csv", header=None, names=columns)
# print(df.columns)
# print(df.head())
# print(df.shape[0])
# print(df.shape[1])
# print(df.dtypes)

columns_to_remove = ["mcc","net", "area", "unit", "samples", "changeable", "created","averageSignal"] 
df_filtered = df.drop(columns=columns_to_remove, axis=1)
# print(df.columns)
# print(df_filtered.head())

df_lte = df_filtered[df_filtered['radio'] == 'LTE'].copy() # Estoy filtraando solo las de LTE
df_lte = df_lte.drop(columns=['radio'], axis=1)
# def generar_id(row): # El valor inicial indica 2G, 3G, 4G, 5G
#     if(row['radio'] == 'GSM'):
#         return f"2_{row['net']}_{row['area']}_{row['cell']}"
#     elif(row['radio'] == 'UMTS'):
#         return f"3_{row['net']}_{row['area']}_{row['cell']}"
#     elif(row['radio'] == 'LTE'):
#         return f"4_{row['net']}_{row['area']}_{row['cell']}"
#     if(row['radio'] == 'NR'):
#         return f"5_{row['net']}_{row['area']}_{row['cell']}"
#     else:
#         return None

# df_filtered['station_id'] = df_filtered.apply(generar_id, axis=1)
# print(df_filtered.columns)

# Suponiendo que df_filtered ya tiene las columnas 'lat' y 'lon'

# Definir límites del área de Madrid
# lat_min, lat_max = 40.30, 40.60
# lon_min, lon_max = -3.90, -3.55

# lat_min, lat_max = 39.88, 41.15
# lon_min, lon_max = -4.58, -3.00

# Filtrar solo las estaciones dentro del área
# df_madrid = df_lte[
#     (df_lte['lat'] >= lat_min) &
#     (df_lte['lat'] <= lat_max) &
#     (df_lte['lon'] >= lon_min) &
#     (df_lte['lon'] <= lon_max)
# ]

print(f"Número de estaciones LTE: {df_lte.shape[0]}")
# Eliminar duplicados basados en la columna 'cell', manteniendo la primera aparición
df_lte = df_lte.drop_duplicates(subset=['cell'], keep='first')

# Imprimir el número de duplicados restantes (debería ser 0)
# print("Duplicadas después de eliminar:", df_lte['cell'].duplicated().sum())
print(f"Número de estaciones LTE después de eliminar duplicadas: {df_lte.shape[0]}")



# duplicados_por_radio = df_madrid.groupby('radio')['station_id'].apply(lambda x: x.duplicated().sum())
# print(duplicados_por_radio)
df_lte.to_csv("LTE_stations_Spain.csv", index=False)
