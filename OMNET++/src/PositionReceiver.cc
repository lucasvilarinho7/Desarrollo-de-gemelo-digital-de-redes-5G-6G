// PositionReceiver.cc
// Servidor UDP que recibe posiciones del UE y las reenvía por TCP a un servidor externo
// ADAPTADO A NUEVO FORMATO: POS,timestamp,x,y,z,sinr,masterId

#include "PositionReceiver.h"

#include "inet/common/packet/Packet.h"
#include "inet/common/packet/chunk/BytesChunk.h"
#include "inet/networklayer/common/L3AddressTag_m.h"
#include "inet/transportlayer/common/L4PortTag_m.h"
#include "inet/common/INETDefs.h"
#include "inet/common/ModuleAccess.h"

#include <sstream>
#include <iostream>
#include <iomanip>

Define_Module(PositionReceiver);

void PositionReceiver::initialize(int stage)
{
    ApplicationBase::initialize(stage);

    if (stage == INITSTAGE_LOCAL) {
        localPort = par("localPort");
        packetsReceived = 0;
        packetReceivedSignal = registerSignal("packetReceived");

        EV_INFO << "PositionReceiver initializing on port " << localPort << endl;

        const char *tcpClientPath = par("tcpClientModule");
        cModule *tcpClientMod = getModuleByPath(tcpClientPath);

        if (tcpClientMod) {
            tcpClient = check_and_cast<TcpClient*>(tcpClientMod);
            std::cout << "[SERVER] TcpClient linked OK\n";
        } else {
            std::cout << "[SERVER WARNING] TcpClient not found!\n";
        }
    }
}

void PositionReceiver::handleStartOperation(LifecycleOperation *operation)
{
    socket.setOutputGate(gate("socketOut"));
    socket.setCallback(this);
    socket.bind(localPort);

    std::cout << "\n========================================\n";
    std::cout << "SERVER: Position Receiver Started\n";
    std::cout << "SERVER: Listening on port " << localPort << "\n";
    std::cout << "========================================\n" << std::endl;
}

void PositionReceiver::handleMessageWhenUp(cMessage *msg)
{
    socket.processMessage(msg);
}

void PositionReceiver::socketDataArrived(UdpSocket *socket, Packet *packet)
{
    packetsReceived++;
    emit(packetReceivedSignal, packetsReceived);

    // Obtener metadatos del paquete
    L3Address srcAddr;
    int srcPort = -1;

    if (auto ind = packet->getTag<L3AddressInd>())
        srcAddr = ind->getSrcAddress();
    if (auto portTag = packet->getTag<L4PortInd>())
        srcPort = portTag->getSrcPort();

    // Obtener payload
    auto chunk = packet->peekAtFront<BytesChunk>();
    std::string payload(chunk->getBytes().begin(), chunk->getBytes().end());

    std::cout << "\n════ POSITION UPDATE RECEIVED ════\n";
    std::cout << "Raw: " << payload << "\n";

    // Parseo NUEVO formato:
    // POS,timestamp,x,y,z,sinr,masterId
    std::string type, token;
    double ts, x, y, z;
    double sinr = -999.0;
    int masterId = -1;

    try {
        std::istringstream iss(payload);

        std::getline(iss, type, ',');
        std::getline(iss, token, ','); ts = std::stod(token);
        std::getline(iss, token, ','); x = std::stod(token);
        std::getline(iss, token, ','); y = std::stod(token);
        std::getline(iss, token, ','); z = std::stod(token);
        std::getline(iss, token, ','); sinr = std::stod(token);
        std::getline(iss, token, ','); masterId = std::stoi(token);

        std::cout << "Packet #" << packetsReceived << "\n";
        std::cout << "UE Source : " << srcAddr << ":" << srcPort << "\n";
        std::cout << "Timestamp : " << ts << "\n";
        std::cout << "Position  : (" << x << ", " << y << ", " << z << ")\n";
        std::cout << "SINR      : " << sinr << " dB\n";
        std::cout << "Master ID : " << masterId << "\n";

        // Forward por TCP
        if (tcpClient) {
            std::ostringstream json;
            json << "{"
                 << "\"type\":\"POS\","
                 << "\"timestamp\":" << ts << ","
                 << "\"ue_id\":\"" << srcAddr.str() << "\","
                 << "\"position\":{\"x\":" << x << ",\"y\":" << y << ",\"z\":" << z << "},"
                 << "\"network\":{\"sinr\":" << sinr
                 << ",\"master_id\":" << masterId << "}"
               //  << "\"sim_time\":" << simTime().dbl()
                 << "}";

            tcpClient->sendToServer(json.str());

            std::cout << "Forwarded via TCP: " << json.str() << "\n";
        }

    } catch (const std::exception &e) {
        std::cout << "[ERROR] Malformed packet: " << e.what() << "\n";
        std::cout << "Payload: " << payload << "\n";
    }

    delete packet;
}

void PositionReceiver::socketErrorArrived(UdpSocket *sock, Indication *indication)
{
    std::cout << "[UDP ERROR] " << indication->str() << "\n";
    delete indication;
}

void PositionReceiver::socketClosed(UdpSocket *sock)
{
    std::cout << "[UDP] Socket closed.\n";
}

void PositionReceiver::handleStopOperation(LifecycleOperation *)
{
    socket.close();
}

void PositionReceiver::handleCrashOperation(LifecycleOperation *)
{
    socket.destroy();
}

void PositionReceiver::finish()
{
    recordScalar("packetsReceived", packetsReceived);
    std::cout << "Simulation ended. Packets received: " << packetsReceived << "\n";
}
