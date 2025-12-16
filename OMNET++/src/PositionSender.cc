// PositionSender.cc
// Aplicación que envía posición y métricas de red (SINR, macNodeId del gNodeB)

#include "PositionSender.h"
#include "inet/common/packet/Packet.h"
#include "inet/common/packet/chunk/BytesChunk.h"
#include "inet/networklayer/common/L3AddressResolver.h"
#include "inet/common/ModuleAccess.h"
#include "common/binder/Binder.h"  // NUEVO: Incluir Binder
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
        // Leer parámetros
        localPort = par("localPort");
        destPort = par("destPort");
        sendInterval = par("sendInterval");
        startTime = par("startTime");

        packetsSent = 0;
        packetSentSignal = registerSignal("packetSent");

        // Crear mensaje de timer
        selfMsg = new cMessage("sendTimer");

        // Inicializar valores por defecto
        lastSinr = -999.0;
        //lastRsrp = -999.0;
        //lastRsrq = -999.0;
        lastMasterNodeId = -1;

        EV_INFO << "PositionSender initialized - will start at " << startTime << endl;
    }
    else if (stage == INITSTAGE_APPLICATION_LAYER) {
        // Obtener módulo de movilidad
        mobility = check_and_cast<IMobility *>(
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

        // ===== ACCESO A MÓDULOS SIMU5G =====

        // Obtener referencia a cellularNic
        cellularNic = getParentModule()->getSubmodule("cellularNic");

        if (cellularNic) {
            EV_INFO << "CellularNic found: " << cellularNic->getFullPath() << endl;

            // Intentar obtener nrPhy (NR) o phy (LTE)
            nrPhy = cellularNic->getSubmodule("nrPhy");
            if (!nrPhy)
                nrPhy = cellularNic->getSubmodule("phy");

            if (nrPhy) {
                EV_INFO << "PHY module found: " << nrPhy->getFullPath() << endl;

                try {
                    // Registrar señales
                    sinrSignal = nrPhy->registerSignal("measuredSinrDl");
                   // rsrpSignal = nrPhy->registerSignal("rsrp");
                   // rsrqSignal = nrPhy->registerSignal("rsrq");

                    // Suscribirse
                    getSimulation()->getSystemModule()->subscribe(sinrSignal, this);
                  //  getSimulation()->getSystemModule()->subscribe(rsrpSignal, this);
                  //  getSimulation()->getSystemModule()->subscribe(rsrqSignal, this);

                  //  std::cout << "[PositionSender] Subscribed to SINR/RSRP/RSRQ signals" << std::endl;
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

        // CRÍTICO: Obtener referencia al Binder (módulo global de Simu5G)
        binder = check_and_cast<Binder*>(
            getSimulation()->getSystemModule()->getSubmodule("binder")
        );

        if (binder) {
            std::cout << "[PositionSender] Binder found: " << binder->getFullPath() << std::endl;
            EV_INFO << "Binder module found" << endl;
        } else {
            std::cout << "[PositionSender] ERROR: Binder not found!" << std::endl;
            EV_ERROR << "Binder module not found - cannot get master node info" << endl;
            throw cRuntimeError("PositionSender: Binder module is required but not found");
        }

        // Programar primer envío
        scheduleAt(simTime() + startTime, selfMsg);

        std::cout << "[PositionSender] Initialized - first send at t="
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
  /*  else if (strcmp(signalName, "rsrp") == 0) {
        lastRsrp = value;
    }
    else if (strcmp(signalName, "rsrq") == 0) {
        lastRsrq = value;
    } */
}

int PositionSender::getMacNodeIdFromBinder()
{
    // MÉTODO CORRECTO: Consultar al Binder por el master node actual
    // El Binder mantiene la información actualizada después de handovers

    if (!binder) {
        std::cout << "[PositionSender] ERROR: Binder reference is null" << std::endl;
        EV_ERROR << "Binder reference is null" << endl;
        return -1;
    }

    cModule *ueModule = getParentModule();
    if (!ueModule) {
        std::cout << "[PositionSender] ERROR: Cannot access UE module" << std::endl;
        return -1;
    }

    try {
        // Obtener el nrMacNodeId del UE (su propio ID)
       MacNodeId ueId = -1;

        if (ueModule->hasPar("nrMacNodeId")) {
            ueId = ueModule->par("nrMacNodeId").intValue();
        }
        else if (ueModule->hasPar("macNodeId")) {
            ueId = ueModule->par("macNodeId").intValue();
        }

        if (ueId <= 0) {
            std::cout << "[PositionSender] ERROR: Invalid UE MacNodeId: " << ueId << std::endl;
            return -1;
        }

        // CLAVE: Usar getNextHop() del Binder para obtener el master node ACTUAL
        // Esta información se actualiza automáticamente durante handovers
        MacNodeId masterNodeId = binder->getNextHop(ueId);

        std::cout << "[PositionSender] UE ID: " << ueId
                  << " → Master Node (from Binder): " << masterNodeId << std::endl;
        EV_INFO << "UE " << ueId << " master node from Binder: " << masterNodeId << endl;

        return masterNodeId;

    } catch (const std::exception& e) {
        EV_ERROR << "Exception in getMacNodeIdFromBinder: " << e.what() << endl;
        std::cout << "[PositionSender] Exception: " << e.what() << std::endl;
    }

    return -1;
}

int PositionSender::getCurrentMasterNodeId()
{
    // Este método ahora simplemente llama a getMacNodeIdFromBinder()
    // que consulta directamente al Binder
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

    // CRÍTICO: Obtener macNodeId ACTUAL del gNodeB conectado desde el Binder
    // Esto se actualiza automáticamente después de handovers
    lastMasterNodeId = getCurrentMasterNodeId();

    // Formato: POS,timestamp,x,y,z,sinr,macNodeId
    std::ostringstream oss;
    oss << std::fixed << std::setprecision(3);
    oss << "POS," << simTime().dbl() << ","
        << pos.x << "," << pos.y << "," << pos.z << ","
        << lastSinr << "," << lastMasterNodeId;

    std::string data = oss.str();

    auto packet = new Packet("PositionPacket");
    auto payload = makeShared<BytesChunk>(
        (const uint8_t*)data.c_str(),
        data.size()
    );
    packet->insertAtBack(payload);

    socket.send(packet);
    packetsSent++;
    emit(packetSentSignal, packetsSent);

    // Log detallado con información de conexión
    std::cout << "\n┌────────────────────────────────────────┐" << std::endl;
    std::cout << "[UE] Packet #" << packetsSent << " SENT" << std::endl;
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

    if (nrPhy) {
        getSimulation()->getSystemModule()->unsubscribe(sinrSignal, this);
       // getSimulation()->getSystemModule()->unsubscribe(rsrpSignal, this);
       // getSimulation()->getSystemModule()->unsubscribe(rsrqSignal, this);
    }

    EV_INFO << "PositionSender stopped" << endl;
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
/*
    std::cout << "\n========================================" << std::endl;
    std::cout << "PositionSender Statistics" << std::endl;
    std::cout << "========================================" << std::endl;
    std::cout << "Total packets sent: " << packetsSent << std::endl;
    std::cout << "========================================\n" << std::endl;
*/
    ApplicationBase::finish();
}
