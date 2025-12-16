import socket
import signal
import sys

HOST = "0.0.0.0"
PORT = 50000

conn = None  # guardará la conexión activa
addr = None

def cerrar_servidor(sig=None, frame=None):
    global conn
    print("\nCerrando servidor...")
    if conn:
        try:
            conn.sendall(b"SERVER_CLOSED")
            conn.close()
            print(f"Notificado al cliente {addr} del cierre.")
        except Exception:
            pass
    s.close()
    print("Servidor cerrado correctamente.")
    sys.exit(0)

# Capturar Ctrl+C para cierre limpio
signal.signal(signal.SIGINT, cerrar_servidor)

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT))
    s.listen(1)
    print(f"Servidor TCP escuchando en {HOST}:{PORT} ...")
    
    while True:
        print("Esperando conexión de un cliente...")
        conn, addr = s.accept()
        with conn:
            print(f"Conexión desde {addr}")
            while True:
                data = conn.recv(1024)
                if not data:
                    print(f"Cliente {addr} desconectado.")
                    break  # salir del bucle interno y volver a aceptar()
                print(f"Recibido: {data.decode('utf-8', errors='replace')}")
                conn.sendall("ACK".encode("utf-8"))