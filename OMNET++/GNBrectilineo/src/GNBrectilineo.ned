package gnbrectilineo;

import simu5g.nodes.NR.gNodeB;
import simu5g.world.radio.LteChannelControl;
import simu5g.common.binder.Binder;
import simu5g.common.carrierAggregation.CarrierAggregation;
import inet.networklayer.configurator.ipv4.Ipv4NetworkConfigurator;
import inet.node.inet.Router;
import inet.visualizer.contract.IIntegratedVisualizer;

network MobileGNB
{
    parameters:
        @display("bgb=600,400");
        // Número de gNodeBs en la red
        int numGnbs = default(1);
        
    submodules:
        
         // Visualizador para mostrar información adicional
        visualizer: <default("IntegratedCanvasVisualizer")> like IIntegratedVisualizer if typename != "" {
            @display("p=50,75");
        }
        channelControl: LteChannelControl {
            @display("p=700,25");
        }
        
        binder: Binder {
            @display("p=700,125");
        }
        
        carrierAggregation: CarrierAggregation {
            @display("p=700,225");
        }
        
        configurator: Ipv4NetworkConfigurator {
            @display("p=700,325");
        }
        
         // Array de gNodeBs móviles
        gNodeB[numGnbs]: MobileGnb {
            @display("p=300,200,row,150;i=device/antennatower"); 
        }     
}