package socketreal.simulations;

import inet.networklayer.configurator.ipv4.Ipv4NetworkConfigurator;
import inet.node.inet.StandardHost;

network SocketRealNetwork
{
    parameters:
        @display("bgb=600,400");

    submodules:
        configurator: Ipv4NetworkConfigurator {
            @display("p=300,50");
        }

        server: StandardHost {
            @display("p=300,200;i=device/server");
        }

    connections allowunconnected:
}