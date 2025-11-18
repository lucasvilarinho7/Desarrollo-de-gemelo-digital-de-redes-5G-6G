package gnbrectilineo;

import simu5g.nodes.NR.gNodeB;

module MobileGnb extends gNodeB
{
    parameters:
        @display("i=device/antennatower");
        
        // Parámetros de cobertura (se usarán en el ini con el visualizador)
        double coverageRange @unit(m) = default(500m);
        
        // Estadísticas de posición
        @statistic[posX](source="xCoord(mobilityPos(mobilityStateChanged))"; record=vector;);
        @statistic[posY](source="yCoord(mobilityPos(mobilityStateChanged))"; record=vector;);
}