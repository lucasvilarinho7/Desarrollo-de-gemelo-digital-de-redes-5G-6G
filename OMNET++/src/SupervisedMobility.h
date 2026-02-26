#ifndef __SUPERVISEDMOBILITY_H_
#define __SUPERVISEDMOBILITY_H_

#include "inet/mobility/base/MovingMobilityBase.h"
#include "inet/common/geometry/common/Coord.h"

using namespace inet;

/**
 * SupervisedMobility: modelo de movilidad para drones controlados
 * externamente por el DroneController (gemelo digital).
 *
 * COMPORTAMIENTO:
 * - Arranca quieto en (initialX, initialY, initialZ)
 * - Cuando recibe setTargetPosition(), comienza a volar hacia el destino
 *   a la velocidad indicada, actualizando posición cada updateInterval
 * - Durante el vuelo emite mobilityStateChanged en cada paso,
 *   lo que hace que Simu5G recalcule SINR/handover continuamente
 * - Al llegar al destino se detiene (velocidad = 0)
 *
 * SEÑALES EMITIDAS:
 * - mobilityStateChanged: en cada paso de movimiento
 *   → LteChannelControl recalcula distancias
 *   → El modelo de propagación recalcula path loss
 *   → Los SINR de todos los UEs se actualizan
 *   → Se disparan handovers si corresponde
 */
class SupervisedMobility : public MovingMobilityBase
{
  protected:
    // Posición destino actual
    Coord targetPosition;

    // ¿Está volando hacia un destino?
    bool isMoving;

    // Velocidad de vuelo actual (m/s)
    double currentSpeed;

    // Velocidad por defecto
    double defaultSpeed;

    // Tolerancia para considerar que llegó al destino (metros)
    static constexpr double ARRIVAL_THRESHOLD = 1.0;

  protected:
    virtual int numInitStages() const override { return NUM_INIT_STAGES; }
    virtual void initialize(int stage) override;

    /**
     * move() es llamado automáticamente por MovingMobilityBase cada
     * updateInterval. Aquí calculamos la nueva posición paso a paso.
     */
    virtual void move() override;

    /**
     * Configura la orientación (heading) hacia el destino.
     */
    void updateOrientation();

  public:
    /**
     * Establece un nuevo destino. El dron comenzará a volar hacia él.
     * Llamado por DroneController.
     *
     * @param target  Coordenadas destino (x, y, z)
     * @param speed   Velocidad en m/s. Si <= 0, usa defaultSpeed.
     */
    void setTargetPosition(const Coord& target, double speed = -1);

    /**
     * Teletransporte inmediato (para compatibilidad / casos especiales).
     */
    void setPositionImmediate(const Coord& newPos);

    /**
     * @return true si el dron está volando hacia un destino
     */
    bool isCurrentlyMoving() const { return isMoving; }

    /**
     * @return distancia restante al destino
     */
    double getRemainingDistance() const;
};

#endif
