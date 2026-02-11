//
// Cliente TCP real integrado en OMNeT++
// Usa sockets del sistema operativo para conectarse a servidor externo
//

#include "inet/common/INETDefs.h"
#include <iostream>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <fcntl.h>
#include <cstring>
#include <errno.h>
#include "Tcpclient.h"

Define_Module(TcpClient);

// Variables globales para el socket real del cliente
static int realClientFd = -1;
static bool isConnected = false;

void TcpClient::initialize()
{
    EV_INFO << "Iniciando cliente TCP en socket real..." << endl;

    const char *SERVER_IP = "127.0.0.1";
    const int SERVER_PORT = 50000;

    // Crear socket real
    realClientFd = ::socket(AF_INET, SOCK_STREAM, 0);
    if (realClientFd < 0) {
        EV_ERROR << "Error creando socket del cliente" << endl;
        std::cerr << "[Cliente] Error creando socket: " << strerror(errno) << std::endl;
        return;
    }

    // Hacer socket no bloqueante
    ::fcntl(realClientFd, F_SETFL, O_NONBLOCK);

    // Configurar dirección del servidor
    struct sockaddr_in serverAddr;
    memset(&serverAddr, 0, sizeof(serverAddr));
    serverAddr.sin_family = AF_INET;
    serverAddr.sin_port = htons(SERVER_PORT);

    if (inet_pton(AF_INET, SERVER_IP, &serverAddr.sin_addr) <= 0) {
        EV_ERROR << "Dirección IP inválida" << endl;
        std::cerr << "[Cliente] Dirección IP inválida" << std::endl;
        ::close(realClientFd);
        realClientFd = -1;
        return;
    }

    // Intentar conexión (no bloqueante)
    int ret = ::connect(realClientFd, (struct sockaddr *)&serverAddr, sizeof(serverAddr));
    if (ret < 0 && errno != EINPROGRESS) {
        EV_ERROR << "Error en connect: " << strerror(errno) << endl;
        std::cerr << "[Cliente] Error conectando: " << strerror(errno) << std::endl;
        ::close(realClientFd);
        realClientFd = -1;
        return;
    }

    std::cout << "[Cliente] Intentando conexión con "
              << SERVER_IP << ":" << SERVER_PORT << std::endl;
    EV_INFO << "Cliente intentando conexión con "
            << SERVER_IP << ":" << SERVER_PORT << endl;

    // Programar verificación periódica
    cMessage *checkMsg = new cMessage("checkConnection");
    scheduleAt(simTime() + 0.1, checkMsg);
}

void TcpClient::handleMessage(cMessage *msg)
{
    if (msg->isSelfMessage() && strcmp(msg->getName(), "checkConnection") == 0) {

        // Verificar si la conexión se ha establecido
        if (!isConnected && realClientFd >= 0) {
            int error = 0;
            socklen_t len = sizeof(error);
            int ret = ::getsockopt(realClientFd, SOL_SOCKET, SO_ERROR, &error, &len);

            if (ret == 0 && error == 0) {
                isConnected = true;
                std::cout << "[Cliente] Conexión establecida" << std::endl;
                EV_INFO << "Conexión establecida exitosamente" << endl;
            }
        }

        // Si está conectado, enviar ACK cada 2 segundos
      /*  if (isConnected && realClientFd >= 0) {
            // Verificar si es momento de enviar (cada 2 segundos)
            double currentTime = simTime().dbl();
            static double lastSendTime = 0.0;

            if (currentTime - lastSendTime >= 2.0) {
                const char *message = "ACK";
                ssize_t sent = ::send(realClientFd, message, strlen(message), 0);

                if (sent > 0) {
                    std::cout << "[Cliente OMNeT++] ACK enviado ("
                              << currentTime << "s)" << std::endl;
                    EV_INFO << "ACK enviado al servidor" << endl;
                    lastSendTime = currentTime;
                } else if (sent < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
                    EV_ERROR << "Error enviando ACK: " << strerror(errno) << endl;
                    std::cerr << "[Cliente] Error enviando: " << strerror(errno) << std::endl;
                    ::close(realClientFd);
                    realClientFd = -1;
                    isConnected = false;
                    delete msg;
                    return;
                }
            } */

            // Leer respuesta del servidor si hay datos
            char buffer[4096];
            ssize_t bytesRead = ::recv(realClientFd, buffer, sizeof(buffer) - 1, 0);

            if (bytesRead > 0) {
                buffer[bytesRead] = '\0';
                std::string receivedMsg(buffer);

                std::cout << "[Cliente OMNeT++] Servidor responde: "
                          << receivedMsg << std::endl;
                EV_INFO << "Respuesta del servidor: " << receivedMsg << endl;

                if (receivedMsg == "SERVER_CLOSED") {
                    std::cout << "[Cliente] Servidor cerró la conexión" << std::endl;
                    EV_WARN << "Servidor cerró la conexión" << endl;
                    ::close(realClientFd);
                    realClientFd = -1;
                    isConnected = false;
                    delete msg;
                    return;
                }
            } else if (bytesRead == 0) {
                std::cout << "[Cliente] Servidor desconectado" << std::endl;
                EV_INFO << "Servidor desconectado" << endl;
                ::close(realClientFd);
                realClientFd = -1;
                isConnected = false;
                delete msg;
                return;
            }
        }

        // Reprogramar el chequeo
        scheduleAt(simTime() + 0.1, msg);
        return;
    }





void TcpClient::sendToServer(const std::string& data)
{
    if (!isConnected || realClientFd < 0)
        return;

    ssize_t sent = ::send(realClientFd, data.c_str(), data.size(), 0);

    if (sent < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
        EV_ERROR << "Error enviando datos al servidor: "
                 << strerror(errno) << endl;
        ::close(realClientFd);
        realClientFd = -1;
        isConnected = false;
    }
}

void TcpClient::finish()
{
    if (realClientFd >= 0) {
        ::close(realClientFd);
        realClientFd = -1;
    }

    isConnected = false;

    std::cout << "[Cliente] Cerrando cliente TCP" << std::endl;
    EV_INFO << "Cliente TCP cerrado" << endl;
}
