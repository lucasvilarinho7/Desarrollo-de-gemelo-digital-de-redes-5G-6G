package dronenetwork;

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

network DroneNetwork
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
            @display("p=2300,275");
        }
        carrierAggregation: CarrierAggregation {
            @display("p=2300,500");
        }

        configurator: Ipv4NetworkConfigurator {
            @display("p=2300,725");
        }
        //routingRecorder: RoutingTableRecorder {
        //    @display("p=2300,925;is=s");
        //}
        droneController: DroneController {
            @display("p=2300,1125");
        }
        upf: Upf {
            @display("p=400,-150");
        }
        router: Router {
            @display("p=700,-150");
        }
        server: StandardHost {
            @display("p=1000,-150;i=device/server");
        }
        gNodeB[numGnb]: MobileGnb {
            @display("p=300,200;i=device/dron");
        }
        ue[numUe]: MobileUE {
            @display("p=500,400;i=device/pocketpc");
        }
       // bgCell[numBgCells]: BackgroundCell {
        //    @display("p=800,400;is=vl");
       // }

    connections allowunconnected:

        server.pppg++ <--> Eth10G <--> router.pppg++;
        router.pppg++ <--> Eth10G <--> upf.filterGate;

        for i=0..numGnb-1 {
            upf.pppg++ <--> Eth10G <--> gNodeB[i].ppp;
        }
        for i=0..numGnb-1 {
            router.pppg++ <--> Eth10G <--> gNodeB[i].pppMEHost;
        }

        gNodeB[0].x2++ <--> Eth10G <--> gNodeB[1].x2++;
        gNodeB[0].x2++ <--> Eth10G <--> gNodeB[2].x2++;
        gNodeB[1].x2++ <--> Eth10G <--> gNodeB[2].x2++;
}
