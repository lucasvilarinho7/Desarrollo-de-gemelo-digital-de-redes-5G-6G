package gnbrectilineo;

import simu5g.nodes.NR.gNodeB;
import simu5g.world.radio.LteChannelControl;
import simu5g.common.binder.Binder;
import simu5g.common.carrierAggregation.CarrierAggregation;
import inet.networklayer.configurator.ipv4.Ipv4NetworkConfigurator;
import inet.node.inet.Router;
import inet.node.inet.StandardHost;
import inet.visualizer.contract.IIntegratedVisualizer;
import inet.node.ethernet.Eth10G;
import simu5g.nodes.Upf;
import simu5g.nodes.backgroundCell.BackgroundCell;
import inet.networklayer.ipv4.RoutingTableRecorder;

network MobileGNB
{
    parameters:
        @display("bgb=2000,2000");
        // Número de gNodeBs en la red
        int numGnb = default(1);

        // Número de UEs en la red
        int numUe = default(1);

        int numBgCells = default(0);

    submodules:

        channelControl: LteChannelControl {
            @display("p=2300,50");
        }

        binder: Binder {
            @display("p=2300,250");
        }      
        carrierAggregation: CarrierAggregation {
            @display("p=2300,450");
        }

        configurator: Ipv4NetworkConfigurator {
            @display("p=2300,650");
        }
        routingRecorder: RoutingTableRecorder {
            @display("p=2300,850;is=s");
        }
        upf: Upf {
            @display("p=400,50");
        }

        // Router para conectar con el core network
        router: Router {
            @display("p=700,50");
        }

        // Servidor para generar tráfico
        server: StandardHost {
            @display("p=1000,50;i=device/server");
        }
		
		// Array de gNodeBs móviles
        gNodeB[numGnb]: MobileGnb {
            @display("p=300,200;i=device/dron");
        }
        // Array de User Equipment
        ue[numUe]: MobileUE {
            @display("p=500,400;i=device/pocketpc");
        }
        
        bgCell[numBgCells]: BackgroundCell {
            @display("p=800,400;is=vl");
        }

    connections allowunconnected:

        // Conexión del servidor al router
        server.pppg++ <--> Eth10G <--> router.pppg++;
        router.pppg++ <--> Eth10G <--> upf.filterGate;

        // Conexiones de gNodeBs al UPF (backhaul - usando array ppp[])
        for i=0..numGnb-1 {
            upf.pppg++ <--> Eth10G <--> gNodeB[i].ppp;
        }
        
        // CONEXIONES X2 CORREGIDAS: Malla completa entre todos los gNodeBs
        // Para 2 gNodeBs: gNodeB[0] <--> gNodeB[1]
        // Para N gNodeBs: cada par (i,j) donde i < j
       // for i=0..numGnb-2, for j=i+1..numGnb-1 {
         //   gNodeB[i].x2++ <--> Eth10G <--> gNodeB[j].x2++;
       // }
              
        
        gNodeB[0].x2++ <--> Eth10G <--> gNodeB[1].x2++;
        
}