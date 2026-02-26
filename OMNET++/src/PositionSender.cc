// PositionSender.cc
// Aplicación que envía posición y métricas de red del UE
// Formato: JSON {"type":"POS","ue_id":...,...}

#include "PositionSender.h"
#include "inet/common/packet/Packet.h"
#include "inet/common/packet/chunk/BytesChunk.h"
#include "inet/networklayer/common/L3AddressResolver.h"
#include "inet/common/ModuleAccess.h"
#include "common/binder/Binder.h"
#include <sstream>
#include <iomanip>

Define_Module(PositionSender);

PositionSender::~PositionSender()
{
    cancelAndDelete(selfMsg);
}

void PositionSender::initialize(int stage)
{
    ApplicationBase::initialize(stage);

    if (stage == INITSTAGE_LOCAL) {
        localPort = par("localPort");
        destPort = par("destPort");
        sendInterval = par("sendInterval");
        startTime = par("startTime");

        packetsSent = 0;
        packetSentSignal = registerSignal("packetSent");

        selfMsg = new cMessage("sendTimer");

        lastSinr = -999.0;
        lastMasterNodeId = -1;

        EV_INFO << "PositionSender initialized - will start at " << startTime << endl;
    }
    else if (stage == INITSTAGE_APPLICATION_LAYER) {
        mobility = check_and_cast<IMobility *>(
            getParentModule()->getSubmodule("mobility")
        );

        socket.setOutputGate(gate("socketOut"));
        socket.setCallback(this);

        const char *destAddrStr = par("destAddress");
        destAddr = L3AddressResolver().resolve(destAddrStr);

        if (localPort != -1)
            socket.bind(localPort);

        socket.connect(destAddr, destPort);

        EV_INFO << "Socket configured - dest: " << destAddr
                << ":" << destPort << endl;

        // ===== OBTENER UE ID =====
        cModule *ueModule = getParentModule();

        // Obtener nrMacNodeId como identificador único del UE
        if (ueModule->hasPar("nrMacNodeId")) {
            ueNodeId = ueModule->par("nrMacNodeId").intValue();
        }
        if (ueNodeId <= 0 && ueModule->hasPar("macNodeId")) {
            ueNodeId = ueModule->par("macNodeId").intValue();
        }

        // Obtener índice del array ue[X]
        const char *fullName = ueModule->getFullName();
        std::string name(fullName);
        size_t start = name.find('[');
        size_t end = name.find(']');
        if (start != std::string::npos && end != std::string::npos) {
            std::string indexStr = name.substr(start + 1, end - start - 1);
            ueIndex = std::stoi(indexStr);
        }

        std::cout << "[PositionSender] UE[" << ueIndex << "] initialized"
                  << " (nrMacNodeId=" << ueNodeId << ")" << std::endl;

        // ===== ACCESO A MÓDULOS SIMU5G =====

        cellularNic = ueModule->getSubmodule("cellularNic");

        if (cellularNic) {
            EV_INFO << "CellularNic found: " << cellularNic->getFullPath() << endl;

            nrPhy = cellularNic->getSubmodule("nrPhy");
            if (!nrPhy)
                nrPhy = cellularNic->getSubmodule("phy");

            if (nrPhy) {
                EV_INFO << "PHY module found: " << nrPhy->getFullPath() << endl;

                try {
                    sinrSignal = nrPhy->registerSignal("measuredSinrDl");
                    getSimulation()->getSystemModule()->subscribe(sinrSignal, this);
                }
                catch (const std::exception& e) {
                    EV_WARN << "Could not subscribe to PHY signals: " << e.what() << endl;
                    std::cout << "[PositionSender] WARNING: " << e.what() << std::endl;
                }
            }
            else {
                EV_WARN << "PHY module not found" << endl;
                std::cout << "[PositionSender] WARNING: PHY module not found!" << std::endl;
            }
        }
        else {
            EV_WARN << "CellularNic not found!" << endl;
            std::cout << "[PositionSender] WARNING: CellularNic not found!" << std::endl;
        }

        binder = check_and_cast<Binder*>(
            getSimulation()->getSystemModule()->getSubmodule("binder")
        );

        if (binder) {
            std::cout << "[PositionSender] Binder found: " << binder->getFullPath() << std::endl;
            EV_INFO << "Binder module found" << endl;
        } else {
            std::cout << "[PositionSender] ERROR: Binder not found!" << std::endl;
            throw cRuntimeError("PositionSender: Binder module is required but not found");
        }

        scheduleAt(simTime() + startTime, selfMsg);

        std::cout << "[PositionSender] First send at t="
                  << (simTime() + startTime) << "s" << std::endl;
    }
}

void PositionSender::receiveSignal(cComponent *source, simsignal_t signalID,
                                    double value, cObject *details)
{
    const char *signalName = getSignalName(signalID);

    if (strcmp(signalName, "measuredSinrDl") == 0) {
        lastSinr = value;
    }
}

int PositionSender::getMacNodeIdFromBinder()
{
    if (!binder) {
        std::cout << "[PositionSender] ERROR: Binder reference is null" << std::endl;
        return -1;
    }

    cModule *ueModule = getParentModule();
    if (!ueModule) {
        return -1;
    }

    try {
        MacNodeId ueId = ueNodeId;

        if (ueId <= 0) {
            return -1;
        }

        MacNodeId masterNodeId = binder->getNextHop(ueId);

        std::cout << "[PositionSender] UE[" << ueIndex << "] ID: " << ueId
                  << " → Master Node: " << masterNodeId << std::endl;

        return masterNodeId;

    } catch (const std::exception& e) {
        EV_ERROR << "Exception in getMacNodeIdFromBinder: " << e.what() << endl;
        std::cout << "[PositionSender] Exception: " << e.what() << std::endl;
    }

    return -1;
}

int PositionSender::getCurrentMasterNodeId()
{
    return getMacNodeIdFromBinder();
}

void PositionSender::handleMessageWhenUp(cMessage *msg)
{
    if (msg == selfMsg) {
        sendPosition();
        scheduleAt(simTime() + sendInterval, selfMsg);
    }
    else {
        socket.processMessage(msg);
    }
}

void PositionSender::sendPosition()
{
    Coord pos = mobility->getCurrentPosition();

    lastMasterNodeId = getCurrentMasterNodeId();

    // Formato JSON con ue_id incluido desde origen
    std::ostringstream json;
    json << std::fixed << std::setprecision(3);
    json << "{"
         << "\"type\":\"POS\","
         << "\"ue_id\":" << ueNodeId << ","
         << "\"ue_index\":" << ueIndex << ","
         << "\"timestamp\":" << simTime().dbl() << ","
         << "\"position\":{"
         << "\"x\":" << pos.x << ","
         << "\"y\":" << pos.y << ","
         << "\"z\":" << pos.z
         << "},"
         << "\"network\":{"
         << "\"sinr\":" << lastSinr << ","
         << "\"master_id\":" << lastMasterNodeId
         << "}"
         << "}";

    std::string data = json.str();

    auto packet = new Packet("PositionPacket");
    auto payload = makeShared<BytesChunk>(
        (const uint8_t*)data.c_str(),
        data.size()
    );
    packet->insertAtBack(payload);

    socket.send(packet);
    packetsSent++;
    emit(packetSentSignal, packetsSent);

    std::cout << "\n┌────────────────────────────────────────┐" << std::endl;
    std::cout << "[UE[" << ueIndex << "]] Packet #" << packetsSent << " SENT" << std::endl;
    std::cout << "  Time       : " << std::fixed << std::setprecision(2) << simTime() << " s" << std::endl;
    std::cout << "  Position   : (" << (int)pos.x << ", " << (int)pos.y << ", " << (int)pos.z << ") m" << std::endl;
    std::cout << "  SINR       : " << std::fixed << std::setprecision(2) << lastSinr << " dB" << std::endl;
    std::cout << "  Connected  : gNodeB[" << (lastMasterNodeId - 1) << "] (macNodeId=" << lastMasterNodeId << ")" << std::endl;
    std::cout << "└────────────────────────────────────────┘\n" << std::endl;

    EV_INFO << "Position sent: (" << pos.x << "," << pos.y << "," << pos.z << ")"
            << " SINR=" << lastSinr << " macNodeId=" << lastMasterNodeId << endl;
}

void PositionSender::handleStartOperation(LifecycleOperation *operation)
{
    EV_INFO << "PositionSender started" << endl;
}

void PositionSender::handleStopOperation(LifecycleOperation *operation)
{
    cancelEvent(selfMsg);
    socket.close();
}

void PositionSender::handleCrashOperation(LifecycleOperation *operation)
{
    cancelEvent(selfMsg);
    socket.destroy();
}

void PositionSender::socketDataArrived(UdpSocket *socket, Packet *packet)
{
    delete packet;
}

void PositionSender::socketErrorArrived(UdpSocket *socket, Indication *indication)
{
    delete indication;
}

void PositionSender::socketClosed(UdpSocket *socket)
{
}

void PositionSender::finish()
{
    recordScalar("packetsSent", packetsSent);
    ApplicationBase::finish();
}
