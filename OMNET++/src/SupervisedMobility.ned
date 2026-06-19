//
// SupervisedMobility.ned
// Movilidad controlada externamente con vuelo gradual hacia destino.
// El DroneController le asigna un destino y una velocidad,
// y este módulo se encarga de volar paso a paso.
//

package dronenetwork;

import inet.mobility.base.MovingMobilityBase;

simple SupervisedMobility extends MovingMobilityBase
{
    parameters:
        @class(SupervisedMobility);

        // Posición inicial (como StationaryMobility)
        double initialX @unit(m) = default(0m);
        double initialY @unit(m) = default(0m);
        double initialZ @unit(m) = default(0m);

        // Velocidad por defecto del dron (m/s), se puede sobreescribir con MOVE
        double defaultSpeed @unit(mps) = default(20mps);

 

        @display("i=block/cogwheel");
}