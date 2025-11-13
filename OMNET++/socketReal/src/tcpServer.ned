

package socketreal;


simple TcpServer extends inet.applications.tcpapp.TcpServerHostApp
{
    parameters:
        @class(TcpServer);
        @display("i=block/app");
        serverThreadModuleType = default("");  // No usado porque usamos sockets reales
}
