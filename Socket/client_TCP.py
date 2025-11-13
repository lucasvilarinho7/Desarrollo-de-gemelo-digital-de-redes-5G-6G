import socket
import signal
import sys

HOST = "127.0.0.1"  
PORT = 50000



        

def cerrar_cliente(sig=None, frame=None):
    print("\nCerrando cliente...")
    s.close()
    print("Cliente cerrado correctamente.")
    sys.exit(0)
    
signal.signal(signal.SIGINT, cerrar_cliente)
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect((HOST, PORT))
    print(f"Conectado a {HOST}:{PORT}")
    
    while True:
        user_input = input("Ingrese un mensaje para enviar al servidor (o 'exit' para salir): ")
        if user_input.lower() == 'exit':
            print("Cerrando la conexión.")
            break
        message = user_input.encode("utf-8")
        s.sendall(message)
        data = s.recv(4096)
        print("Respuesta del servidor:", data.decode("utf-8", errors="replace"))
        if data == b"SERVER_CLOSED":
            print("El servidor ha cerrado la conexión.")
            break
