//
// DroneController.ned
// Módulo que recibe comandos del Gemelo Digital y modifica
// la posición de los gNodeB móviles (drones) en tiempo real.
//

package gnbrectilineo;

simple DroneController
{
    parameters:
        double checkInterval @unit(s) = default(0.5s);  // Intervalo de chequeo de comandos
        @display("i=block/control;is=s");
}