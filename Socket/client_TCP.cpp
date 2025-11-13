#include <iostream>
#include <csignal>
#include <unistd.h>
#include <cstring>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <cstdlib>

int sock = -1;

void cerrar_cliente(int signum) {
    std::cout << "\nCerrando cliente..." << std::endl;
    if (sock != -1) close(sock);
    std::cout << "Cliente cerrado correctamente." << std::endl;
    exit(0);
}

int main() {
    signal(SIGINT, cerrar_cliente);

    const char* HOST = "127.0.0.1";
    const int PORT = 50000;

    sock = socket(AF_INET, SOCK_STREAM, 0);
    if (sock < 0) { perror("socket"); return 1; }

    sockaddr_in server_addr{};
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons(PORT);
    inet_pton(AF_INET, HOST, &server_addr.sin_addr);

    if (connect(sock, (struct sockaddr*)&server_addr, sizeof(server_addr)) < 0) {
        perror("connect"); return 1;
    }

    std::cout << "Conectado a " << HOST << ":" << PORT << std::endl;

    while (true) {
        std::cout << "Ingrese un mensaje (o 'exit' para salir): ";
        std::string input;
        std::getline(std::cin, input);

        if (input == "exit") {
            std::cout << "Cerrando la conexión." << std::endl;
            break;
        }

        send(sock, input.c_str(), input.length(), 0);

        char buffer[4096];
        ssize_t bytes = recv(sock, buffer, sizeof(buffer)-1, 0);
        if (bytes <= 0) {
            std::cout << "Servidor cerró la conexión." << std::endl;
            break;
        }
        buffer[bytes] = '\0';

        if (strcmp(buffer, "SERVER_CLOSED") == 0) {
            std::cout << "El servidor ha cerrado la conexión." << std::endl;
            break;
        }

        std::cout << "Respuesta del servidor: " << buffer << std::endl;
    }

    close(sock);
    std::cout << "Cliente desconectado." << std::endl;
    return 0;
}
