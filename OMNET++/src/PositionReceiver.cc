// PositionReceiver.cc
// Servidor UDP que recibe mensajes JSON del UE y del gNodeB
// y los reenvía por TCP al servidor Python externo
// Formatos JSON:
//   UE:     {"type":"POS","ue_id":...,"ue_index":...,...}
//   gNodeB: {"type":"COVERAGE","gnb_id":...,...}

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
    std::cout << "SERVER: All messages in JSON format\n";
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

    // Verificar que es JSON
    size_t firstBrace = payload.find('{');
    if (firstBrace == std::string::npos) {
        std::cout << "\n[WARN] Non-JSON message: " << payload.substr(0, 60) << "\n";
        delete packet;
        return;
    }

    // Detectar tipo por contenido
    if (payload.find("\"POS\"") != std::string::npos) {
        handlePositionMessage(payload, srcAddr, srcPort);
    }
    else if (payload.find("\"COVERAGE\"") != std::string::npos) {
        handleCoverageMessage(payload, srcAddr, srcPort);
    }
    else {
        std::cout << "\n[WARN] Unknown JSON type: " << payload.substr(0, 80) << "\n";
    }

    delete packet;
}

void PositionReceiver::handlePositionMessage(const std::string &payload,
                                              const L3Address &srcAddr,
                                              int srcPort)
{
    std::cout << "\n════ UE POSITION UPDATE #" << packetsReceived << " ════\n";
    std::cout << "Source : " << srcAddr << ":" << srcPort << "\n";
    std::cout << "JSON   : " << payload << "\n";

    // JSON ya incluye ue_id y ue_index desde el PositionSender
    // Reenviar directamente por TCP
    if (tcpClient) {
        tcpClient->sendToServer(payload);
        std::cout << "Forwarded POS via TCP ✓\n";
    }
}

void PositionReceiver::handleCoverageMessage(const std::string &payload,
                                              const L3Address &srcAddr,
                                              int srcPort)
{
    std::cout << "\n���═══ gNodeB COVERAGE UPDATE #" << packetsReceived << " ════\n";
    std::cout << "Source : " << srcAddr << ":" << srcPort << "\n";
    std::cout << "JSON   : " << payload << "\n";

    if (tcpClient) {
        tcpClient->sendToServer(payload);
        std::cout << "Forwarded COVERAGE via TCP ✓\n";
    } else {
        std::cout << "[WARN] TcpClient not available\n";
    }
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
