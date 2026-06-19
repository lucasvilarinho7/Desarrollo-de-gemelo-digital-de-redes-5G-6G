// GnbSender.cc
// Aplicación que envía información periódica del gNodeB al servidor
// Formato: JSON {"type":"GNB_Report",...}

#include "GnbSender.h"
#include "inet/common/packet/Packet.h"
#include "inet/common/packet/chunk/BytesChunk.h"
#include "inet/networklayer/common/L3AddressResolver.h"
#include "inet/common/ModuleAccess.h"
#include "common/binder/Binder.h"
#include "stack/mac/layer/LteMacEnb.h"
#include <sstream>
#include <iomanip>
#include <algorithm>

Define_Module(GnbSender);

GnbSender::~GnbSender()
{
    cancelAndDelete(selfMsg);
}

void GnbSender::initialize(int stage)
{
    ApplicationBase::initialize(stage);

    if (stage == INITSTAGE_LOCAL) {
        // Leer parámetros
        localPort = par("localPort");
        destPort = par("destPort");
        sendInterval = par("sendInterval");
        startTime = par("startTime");

        packetsSent = 0;
        packetSentSignal = registerSignal("packetSent");

        // Crear mensaje de timer
        selfMsg = new cMessage("sendTimer");

        EV_INFO << "GnbSender initialized - will start at " << startTime << endl;
    }
    else if (stage == INITSTAGE_APPLICATION_LAYER) {
        // Obtener módulo de movilidad
        mobility = check_and_cast<IMobility*>(
            getParentModule()->getSubmodule("mobility")
        );

        // Configurar socket UDP
        socket.setOutputGate(gate("socketOut"));
        socket.setCallback(this);

        // Resolver dirección destino
        const char *destAddrStr = par("destAddress");
        destAddr = L3AddressResolver().resolve(destAddrStr);

        if (localPort != -1)
            socket.bind(localPort);

        socket.connect(destAddr, destPort);

        EV_INFO << "Socket configured - dest: " << destAddr
                << ":" << destPort << endl;

        // ===== OBTENER INFORMACIÓN DEL GNODEB =====

        cModule *gnbModule = getParentModule();

        if (gnbModule->hasPar("macCellId")) {
            macCellId = gnbModule->par("macCellId").intValue();
        }
        if (gnbModule->hasPar("macNodeId")) {
            macNodeId = gnbModule->par("macNodeId").intValue();
        }

        // Obtener el índice del array (gNodeB[0], gNodeB[1], etc.)
        const char *fullName = gnbModule->getFullName();
        std::string name(fullName);

        size_t start = name.find('[');
        size_t end = name.find(']');
        if (start != std::string::npos && end != std::string::npos) {
            std::string indexStr = name.substr(start + 1, end - start - 1);
            gnbIndex = std::stoi(indexStr);
        }

        std::cout << "[GnbSender] gNodeB[" << gnbIndex << "] initialized"
                  << " (macCellId=" << macCellId
                  << ", macNodeId=" << macNodeId << ")" << std::endl;

        // Obtener referencia al Binder
        binder = check_and_cast<Binder*>(
            getSimulation()->getSystemModule()->getSubmodule("binder")
        );

        if (!binder) {
            throw cRuntimeError("GnbSender: Binder module not found");
        }

        // Obtener referencia a cellularNic
        cellularNic = gnbModule->getSubmodule("cellularNic");
        if (!cellularNic) {
            throw cRuntimeError("GnbSender: cellularNic module not found");
        }

        // Programar primer envío
        scheduleAt(simTime() + startTime, selfMsg);

        std::cout << "[GnbSender] First send scheduled at t="
                  << (simTime() + startTime) << "s" << std::endl;
    }
}

std::vector<int> GnbSender::getConnectedUeIds()
{
    std::vector<int> connectedUes;

    if (!binder) {
        return connectedUes;
    }

    try {
        // ============================================================
        // MÉTODO CORREGIDO: Recorrer TODOS los UEs registrados en la red
        // y consultar al Binder cuál es su master node actual.
        //
        // En Simu5G, los macNodeIds se asignan secuencialmente:
        //   - gNodeBs: empiezan en 1 (macNodeId=1, 2, ...)
        //   - UEs NR:  empiezan desde 2048+ (nrMacNodeId)
        //
        // El Binder::getNextHop(ueId) devuelve el macNodeId del gNodeB
        // al que está conectado ese UE. Si el UE no existe o no está
        // conectado, devuelve 0.
        // ============================================================

        // Recorrer los UEs de la simulación directamente desde los módulos
        cModule *network = getSimulation()->getSystemModule();
        int numUe = 0;

        if (network->hasPar("numUe")) {
            numUe = network->par("numUe").intValue();
        }

        for (int i = 0; i < numUe; i++) {
            std::string uePath = "ue[" + std::to_string(i) + "]";
            cModule *ueModule = network->getSubmodule("ue", i);

            if (!ueModule) continue;

            // Obtener el nrMacNodeId del UE (ID NR asignado por Simu5G)
            MacNodeId ueNrId = 0;
            if (ueModule->hasPar("nrMacNodeId")) {
                ueNrId = ueModule->par("nrMacNodeId").intValue();
            }
            // Fallback: intentar macNodeId
            if (ueNrId == 0 && ueModule->hasPar("macNodeId")) {
                ueNrId = ueModule->par("macNodeId").intValue();
            }

            if (ueNrId == 0) continue;

            // Consultar al Binder: ¿cuál es el next hop (master gNodeB) de este UE?
            MacNodeId masterNode = binder->getNextHop(ueNrId);

            // Comparar con el macNodeId de ESTE gNodeB
            if ((int)masterNode == macNodeId) {
                connectedUes.push_back(ueNrId);
            }
        }

        // DEBUG: Log del escaneo
        if (connectedUes.empty()) {
            EV_DEBUG << "[GnbSender] gNodeB[" << gnbIndex
                     << "] No UEs found connected (macNodeId=" << macNodeId << ")" << endl;
        }

    } catch (const std::exception& e) {
        EV_ERROR << "Error getting connected UEs: " << e.what() << endl;
        std::cout << "[GnbSender] ERROR in getConnectedUeIds: " << e.what() << std::endl;
    }

    return connectedUes;
}

int GnbSender::getNumConnectedUes()
{
    return getConnectedUeIds().size();
}

void GnbSender::handleMessageWhenUp(cMessage *msg)
{
    if (msg == selfMsg) {
        sendGnbInfo();
        scheduleAt(simTime() + sendInterval, selfMsg);
    }
    else {
        socket.processMessage(msg);
    }
}

void GnbSender::sendGnbInfo()
{
    Coord pos = mobility->getCurrentPosition();
    std::vector<int> connectedUes = getConnectedUeIds();
    int numConnected = connectedUes.size();

    // Formato JSON
    std::ostringstream json;
    json << std::fixed << std::setprecision(3);
    json << "{"
         << "\"type\":\"GNB_Report\","
         << "\"timestamp\":" << simTime().dbl() << ","
         << "\"gnb_id\":" << macNodeId << ","
         << "\"gnb_index\":" << gnbIndex << ","
         << "\"position\":{"
         << "\"x\":" << pos.x << ","
         << "\"y\":" << pos.y << ","
         << "\"z\":" << pos.z
         << "},"
         << "\"num_connected\":" << numConnected << ","
         << "\"connected_ues\":[";

    for (size_t i = 0; i < connectedUes.size(); i++) {
        json << connectedUes[i];
        if (i < connectedUes.size() - 1) json << ",";
    }

    json << "]}";

    std::string data = json.str();

    auto packet = new Packet("GnbInfoPacket");
    auto payload = makeShared<BytesChunk>(
        (const uint8_t*)data.c_str(),
        data.size()
    );
    packet->insertAtBack(payload);

    socket.send(packet);
    packetsSent++;
    emit(packetSentSignal, packetsSent);

    // Log detallado
    std::cout << "\n┌────────────────────────────────────────┐" << std::endl;
    std::cout << "[gNodeB[" << gnbIndex << "]] Info Packet #" << packetsSent << " SENT" << std::endl;
    std::cout << "  Time       : " << std::fixed << std::setprecision(2)
              << simTime() << " s" << std::endl;
    std::cout << "  Position   : (" << (int)pos.x << ", " << (int)pos.y
              << ", " << (int)pos.z << ") m" << std::endl;
    std::cout << "  Connected  : " << numConnected << " UEs";

    if (numConnected > 0) {
        std::cout << " [";
        for (size_t i = 0; i < connectedUes.size(); i++) {
            std::cout << connectedUes[i];
            if (i < connectedUes.size() - 1) std::cout << ", ";
        }
        std::cout << "]";
    }
    std::cout << std::endl;
    std::cout << "└────────────────────────────────────────┘\n" << std::endl;

    EV_INFO << "GnbInfo sent: pos(" << pos.x << "," << pos.y << "," << pos.z << ")"
            << " UEs=" << numConnected << endl;
}

void GnbSender::handleStartOperation(LifecycleOperation *operation)
{
    EV_INFO << "GnbSender started" << endl;
}

void GnbSender::handleStopOperation(LifecycleOperation *operation)
{
    cancelEvent(selfMsg);
    socket.close();
    EV_INFO << "GnbSender stopped" << endl;
}

void GnbSender::handleCrashOperation(LifecycleOperation *operation)
{
    cancelEvent(selfMsg);
    socket.destroy();
}

void GnbSender::socketDataArrived(UdpSocket *socket, Packet *packet)
{
    delete packet;
}

void GnbSender::socketErrorArrived(UdpSocket *socket, Indication *indication)
{
    delete indication;
}

void GnbSender::socketClosed(UdpSocket *socket)
{
}

void GnbSender::finish()
{
    recordScalar("packetsSent", packetsSent);
    ApplicationBase::finish();
}
