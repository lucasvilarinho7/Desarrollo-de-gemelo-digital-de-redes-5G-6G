package gnbrectilineo;

import simu5g.nodes.NR.gNodeB;

module MobileGnb extends gNodeB
{
    parameters:
        @display("i=device/dron");
        
        // NO sobreescribir macCellId ni macNodeId aquí
        // Deben ser configurados en omnetpp.ini
        
        // Estadísticas de posición
        @statistic[posX](source="xCoord(mobilityPos(mobilityStateChanged))"; record=vector;);
        @statistic[posY](source="yCoord(mobilityPos(mobilityStateChanged))"; record=vector;);
        
        // Estadísticas de handover y conexiones
        @statistic[handoverCount](title="Handover Count"; source="handoverCompleted"; record=count,vector;);
        @statistic[connectedUes](title="Connected UEs"; source="numConnectedUes"; record=vector,stats;);
}