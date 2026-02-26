//
// DroneController.cc
// Procesa comandos MOVE y los aplica sobre SupervisedMobility
//

#include "DroneController.h"
#include "SupervisedMobility.h"
#include "inet/common/geometry/common/Coord.h"

#include <iostream>
#include <regex>

using namespace inet;

Define_Module(DroneController);

void DroneController::initialize()
{
    checkInterval = par("checkInterval").doubleValue();

    checkMsg = new cMessage("checkDroneCommands");
    scheduleAt(simTime() + checkInterval, checkMsg);

    std::cout << "[DroneController] Inicializado. "
              << "Intervalo de chequeo: " << checkInterval << "s"
              << std::endl;
}

void DroneController::enqueueCommand(const std::string& jsonCmd)
{
    std::lock_guard<std::mutex> lock(cmdMutex);
    pendingCommands.push(jsonCmd);
    std::cout << "[DroneController] Comando encolado (cola: "
              << pendingCommands.size() << ")" << std::endl;
}

void DroneController::handleMessage(cMessage *msg)
{
    if (msg != checkMsg) {
        delete msg;
        return;
    }

    // Extraer todos los comandos pendientes
    std::queue<std::string> toProcess;
    {
        std::lock_guard<std::mutex> lock(cmdMutex);
        std::swap(toProcess, pendingCommands);
    }

    while (!toProcess.empty()) {
        processCommand(toProcess.front());
        toProcess.pop();
    }

    scheduleAt(simTime() + checkInterval, checkMsg);
}

void DroneController::processCommand(const std::string& jsonCmd)
{
    std::cout << "[DroneController] Procesando: " << jsonCmd << std::endl;

    try {
        // Parsear campos del JSON con regex
        auto extractInt = [&](const std::string& field) -> int {
            std::regex re("\"" + field + "\"\\s*:\\s*(\\d+)");
            std::smatch m;
            if (std::regex_search(jsonCmd, m, re)) return std::stoi(m[1]);
            return -1;
        };

        auto extractDouble = [&](const std::string& field) -> double {
            std::regex re("\"" + field + "\"\\s*:\\s*([\\d.\\-]+)");
            std::smatch m;
            if (std::regex_search(jsonCmd, m, re)) return std::stod(m[1]);
            return -1.0;
        };

        if (jsonCmd.find("\"MOVE_BATCH\"") != std::string::npos) {
            // Batch: extraer cada bloque {...} dentro de "moves":[...]
            std::regex moveBlock("\\{[^}]*\"gnb_index\"[^}]*\\}");
            auto begin = std::sregex_iterator(jsonCmd.begin(), jsonCmd.end(), moveBlock);
            auto end = std::sregex_iterator();

            for (auto it = begin; it != end; ++it) {
                std::string block = it->str();
                // Crear lambdas locales para el bloque
                auto eInt = [&](const std::string& f) -> int {
                    std::regex re("\"" + f + "\"\\s*:\\s*(\\d+)");
                    std::smatch m;
                    if (std::regex_search(block, m, re)) return std::stoi(m[1]);
                    return -1;
                };
                auto eDbl = [&](const std::string& f) -> double {
                    std::regex re("\"" + f + "\"\\s*:\\s*([\\d.\\-]+)");
                    std::smatch m;
                    if (std::regex_search(block, m, re)) return std::stod(m[1]);
                    return -1.0;
                };

                int idx = eInt("gnb_index");
                double x = eDbl("x"), y = eDbl("y"), z = eDbl("z");
                double speed = eDbl("speed");
                if (idx >= 0) applyMove(idx, x, y, z, speed);
            }
        }
        else if (jsonCmd.find("\"MOVE\"") != std::string::npos) {
            int idx = extractInt("gnb_index");
            double x = extractDouble("x");
            double y = extractDouble("y");
            double z = extractDouble("z");
            double speed = extractDouble("speed");  // -1 si no viene
            if (idx >= 0) applyMove(idx, x, y, z, speed);
        }
        else {
            std::cout << "[DroneController] Comando no reconocido" << std::endl;
        }
    }
    catch (const std::exception& e) {
        std::cerr << "[DroneController] Error: " << e.what() << std::endl;
    }
}

void DroneController::applyMove(int gnbIndex, double x, double y, double z,
                                 double speed)
{
    cModule *network = getSystemModule();
    cModule *gnb = network->getSubmodule("gNodeB", gnbIndex);
    if (!gnb) {
        std::cerr << "[DroneController] ERROR: gNodeB[" << gnbIndex
                  << "] no existe" << std::endl;
        return;
    }

    cModule *mobilityMod = gnb->getSubmodule("mobility");
    if (!mobilityMod) {
        std::cerr << "[DroneController] ERROR: mobility no encontrado"
                  << std::endl;
        return;
    }

    // Cast a SupervisedMobility
    SupervisedMobility *mobility = dynamic_cast<SupervisedMobility*>(mobilityMod);
    if (!mobility) {
        std::cerr << "[DroneController] ERROR: gNodeB[" << gnbIndex
                  << "] no usa SupervisedMobility. "
                  << "Tipo actual: " << mobilityMod->getClassName()
                  << std::endl;
        return;
    }

    // Obtener posición actual para el log
    Coord oldPos = mobility->getCurrentPosition();
    Coord target(x, y, z);
    double distance = oldPos.distance(target);

    std::cout << "\n[DroneController] MOVE gNodeB[" << gnbIndex << "]:"
              << std::endl;
    std::cout << "  Actual:    (" << oldPos.x << ", " << oldPos.y
              << ", " << oldPos.z << ")" << std::endl;
    std::cout << "  Destino:   (" << x << ", " << y << ", " << z << ")"
              << std::endl;
    std::cout << "  Distancia: " << distance << " m" << std::endl;
    std::cout << "  Velocidad: " << (speed > 0 ? speed : -1) << " m/s"
              << (speed <= 0 ? " (usara defaultSpeed)" : "") << std::endl;

    // Iniciar vuelo gradual
    mobility->setTargetPosition(target, speed);
}

void DroneController::finish()
{
    cancelAndDelete(checkMsg);
    checkMsg = nullptr;
    std::cout << "[DroneController] Finalizado" << std::endl;
}
