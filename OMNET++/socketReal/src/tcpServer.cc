//
// Servidor TCP real integrado en OMNeT++
// Usa sockets del sistema operativo para aceptar conexiones externas
//

#include "tcpServer.h"
#include "inet/common/INETDefs.h"
#include <iostream>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <fcntl.h>
#include <cstring>

Define_Module(TcpServer);

// Variables globales para los file descriptors (sockets reales del SO)
int realServerFd = -1;
int realClientFd = -1;

void TcpServer::initialize()
{
    EV_INFO << "Iniciando servidor TCP en socket real..." << endl;

    // Crear socket real
    realServerFd = ::socket(AF_INET, SOCK_STREAM, 0);
    if (realServerFd < 0) {
        EV_ERROR << "Error creando socket" << endl;
        std::cerr << "[Servidor] Error creando socket" << std::endl;
        return;
    }

    // Permitir reutilizar dirección
    int opt = 1;
    ::setsockopt(realServerFd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    // Configurar dirección
    struct sockaddr_in address;
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = INADDR_ANY;
    address.sin_port = htons(50000);

    // Bind
    if (::bind(realServerFd, (struct sockaddr *)&address, sizeof(address)) < 0) {
        EV_ERROR << "Error en bind" << endl;
        std::cerr << "[Servidor] Error en bind. ¿Puerto 50000 en uso?" << std::endl;
        ::close(realServerFd);
        realServerFd = -1;
        return;
    }

    // Listen
    if (::listen(realServerFd, 3) < 0) {
        EV_ERROR << "Error en listen" << endl;
        std::cerr << "[Servidor] Error en listen" << std::endl;
        ::close(realServerFd);
        realServerFd = -1;
        return;
    }

    // Hacer el socket no bloqueante
    ::fcntl(realServerFd, F_SETFL, O_NONBLOCK);

    std::cout << "[Servidor] Escuchando en puerto 50000..." << std::endl;
    EV_INFO << "Servidor TCP escuchando en puerto 50000" << endl;

    // Programar verificación periódica
    cMessage *checkMsg = new cMessage("checkConnection");
    scheduleAt(simTime() + 0.1, checkMsg);
}

void TcpServer::handleMessage(cMessage *msg)
{
    if (msg->isSelfMessage() && strcmp(msg->getName(), "checkConnection") == 0) {
        // Verificar nuevas conexiones
        if (realClientFd < 0 && realServerFd >= 0) {
            struct sockaddr_in clientAddr;
            socklen_t addrLen = sizeof(clientAddr);
            realClientFd = ::accept(realServerFd, (struct sockaddr *)&clientAddr, &addrLen);

            if (realClientFd >= 0) {
                ::fcntl(realClientFd, F_SETFL, O_NONBLOCK);
                std::cout << "[Servidor] Cliente conectado desde "
                          << inet_ntoa(clientAddr.sin_addr) << std::endl;
                EV_INFO << "Cliente conectado" << endl;
            }
        }

        // Leer datos del cliente si está conectado
        if (realClientFd >= 0) {
            char buffer[4096];
            ssize_t bytesRead = ::recv(realClientFd, buffer, sizeof(buffer) - 1, 0);

            if (bytesRead > 0) {
                buffer[bytesRead] = '\0';
                std::string receivedMsg(buffer);

                std::cout << "[Servidor OMNeT++] Recibido: " << receivedMsg << std::endl;
                EV_INFO << "Mensaje recibido: " << receivedMsg << endl;

                // Enviar eco de vuelta
                ::send(realClientFd, buffer, bytesRead, 0);
                std::cout << "[Servidor OMNeT++] Eco enviado" << std::endl;
            } else if (bytesRead == 0) {
                std::cout << "[Servidor] Cliente desconectado" << std::endl;
                EV_INFO << "Cliente desconectado" << endl;
                ::close(realClientFd);
                realClientFd = -1;
            }
        }

        // Reprogramar el chequeo
        scheduleAt(simTime() + 0.1, msg);
        return;
    }

    // Cualquier otro mensaje (no debería ocurrir normalmente)
    EV_WARN << "Mensaje desconocido recibido por TcpServer: " << msg->getName() << endl;
    delete msg;
}

void TcpServer::finish()
{
    if (realClientFd >= 0) {
        ::close(realClientFd);
        realClientFd = -1;
    }
    if (realServerFd >= 0) {
        ::close(realServerFd);
        realServerFd = -1;
    }

    std::cout << "[Servidor] Cerrando servidor TCP" << std::endl;
    EV_INFO << "Servidor TCP cerrado" << endl;
}
