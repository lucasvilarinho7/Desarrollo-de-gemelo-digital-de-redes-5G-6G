//
// SupervisedMobility.cc
// Movilidad con vuelo gradual controlada por el DroneController
//

#include "SupervisedMobility.h"

Define_Module(SupervisedMobility);

void SupervisedMobility::initialize(int stage)
{
    MovingMobilityBase::initialize(stage);

    if (stage == INITSTAGE_LOCAL) {
        // Leer posición inicial desde parámetros NED/INI
        lastPosition.x = par("initialX").doubleValue();
        lastPosition.y = par("initialY").doubleValue();
        lastPosition.z = par("initialZ").doubleValue();

        // Estado inicial: quieto
        targetPosition = lastPosition;
        isMoving = false;

        // Velocidad por defecto
        defaultSpeed = par("defaultSpeed").doubleValue();
        currentSpeed = 0;

        // Velocidad cero → no se mueve hasta recibir orden
        lastVelocity = Coord::ZERO;

        std::cout << "[SupervisedMobility] Inicializado en ("
                  << lastPosition.x << ", " << lastPosition.y << ", "
                  << lastPosition.z << ") speed_default=" << defaultSpeed
                  << " m/s" << std::endl;
    }
}

// ─────────────────────────────────────────────────────────────
//  move() - Llamado automáticamente cada updateInterval por
//  MovingMobilityBase. Es el "corazón" del vuelo.
//
//  Si isMoving == true:
//    1. Calcula cuánto puede avanzar en este intervalo
//    2. Si la distancia restante es menor → llega al destino
//    3. Si no → avanza en línea recta
//    4. MovingMobilityBase emite mobilityStateChanged automáticamente
//
//  Si isMoving == false:
//    - lastVelocity = (0,0,0) → el nodo se queda quieto
// ─────────────────────────────────────────────────────────────
void SupervisedMobility::move()
{
    if (!isMoving) {
        // Quieto: velocidad cero, no hacer nada
        lastVelocity = Coord::ZERO;
        return;
    }

    // Vector desde posición actual al destino
    Coord direction = targetPosition - lastPosition;
    double remainingDistance = direction.length();

    // ¿Llegamos?
    if (remainingDistance <= ARRIVAL_THRESHOLD) {
        // Snap a la posición exacta del destino
        lastPosition = targetPosition;
        lastVelocity = Coord::ZERO;
        isMoving = false;
        currentSpeed = 0;

        std::cout << "\n[SupervisedMobility] >>> DESTINO ALCANZADO <<<"
                  << std::endl;
        std::cout << "  Posicion final: (" << lastPosition.x << ", "
                  << lastPosition.y << ", " << lastPosition.z << ")"
                  << std::endl;
        std::cout << "  SimTime: " << simTime() << "s\n" << std::endl;
        return;
    }

    // Calcular cuánto podemos avanzar en este intervalo
    // updateInterval viene de MovingMobilityBase
    double timeStep = updateInterval.dbl();
    double stepDistance = currentSpeed * timeStep;

    if (stepDistance >= remainingDistance) {
        // En este paso llegamos al destino
        lastPosition = targetPosition;
        lastVelocity = Coord::ZERO;
        isMoving = false;
        currentSpeed = 0;

        std::cout << "[SupervisedMobility] Destino alcanzado (en paso)"
                  << std::endl;
    }
    else {
        // Avanzar una fracción en la dirección del destino
        Coord unitDirection = direction / remainingDistance;  // normalizar
        lastPosition += unitDirection * stepDistance;

        // Actualizar velocidad (vector) para que INET lo refleje
        lastVelocity = unitDirection * currentSpeed;
    }
}

// ─────────────────────────────────────────────────────────────
//  setTargetPosition() - Llamado por DroneController
//
//  Inicia el vuelo hacia el destino. El dron se moverá
//  gradualmente paso a paso en los siguientes move().
// ─────────────────────────────────────────────────────────────
void SupervisedMobility::setTargetPosition(const Coord& target, double speed)
{
    // Si la velocidad no se especifica, usar la por defecto
    if (speed <= 0) {
        speed = defaultSpeed;
    }

    Coord oldPos = lastPosition;
    targetPosition = target;
    currentSpeed = speed;
    isMoving = true;

    // Calcular distancia y tiempo estimado de vuelo
    double distance = oldPos.distance(target);
    double eta = (speed > 0) ? distance / speed : 0;

    // Calcular dirección inicial para el log
    Coord direction = target - oldPos;
    double angle = atan2(direction.y, direction.x) * 180.0 / M_PI;

    // Establecer velocidad vectorial inicial
    if (distance > ARRIVAL_THRESHOLD) {
        Coord unitDir = direction / distance;
        lastVelocity = unitDir * currentSpeed;
    }

    std::cout << "\n============================================" << std::endl;
    std::cout << "[SupervisedMobility] VUELO INICIADO" << std::endl;
    std::cout << "============================================" << std::endl;
    std::cout << "  Origen:    (" << oldPos.x << ", " << oldPos.y
              << ", " << oldPos.z << ")" << std::endl;
    std::cout << "  Destino:   (" << target.x << ", " << target.y
              << ", " << target.z << ")" << std::endl;
    std::cout << "  Distancia: " << distance << " m" << std::endl;
    std::cout << "  Velocidad: " << speed << " m/s" << std::endl;
    std::cout << "  Angulo:    " << angle << " grados" << std::endl;
    std::cout << "  ETA:       " << eta << " s" << std::endl;
    std::cout << "  SimTime:   " << simTime() << "s" << std::endl;
    std::cout << "============================================\n" << std::endl;
}

// ─────────────────────────────────────────────────────────────
//  setPositionImmediate() - Teletransporte (para debug/emergencia)
// ─────────────────────────────────────────────────────────────
void SupervisedMobility::setPositionImmediate(const Coord& newPos)
{
    lastPosition = newPos;
    targetPosition = newPos;
    lastVelocity = Coord::ZERO;
    isMoving = false;
    currentSpeed = 0;

    // Forzar emisión de señal para que Simu5G recalcule
    emitMobilityStateChangedSignal();

    std::cout << "[SupervisedMobility] TELETRANSPORTE a ("
              << newPos.x << ", " << newPos.y << ", " << newPos.z
              << ")" << std::endl;
}

double SupervisedMobility::getRemainingDistance() const
{
    if (!isMoving) return 0;
    return lastPosition.distance(targetPosition);
}
