//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Lesser General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU Lesser General Public License for more details.
//
// You should have received a copy of the GNU Lesser General Public License
// along with this program.  If not, see http://www.gnu.org/licenses/.
//

#ifndef __SOCKETREAL_TCPSERVER_H_
#define __SOCKETREAL_TCPSERVER_H_

#include <omnetpp.h>

using namespace omnetpp;

/**
 * Servidor TCP que usa sockets reales del sistema operativo
 * para comunicarse con aplicaciones externas
 */
class TcpServer : public cSimpleModule
{
  protected:
    virtual void initialize() override;
    virtual void handleMessage(cMessage *msg) override;
    virtual void finish() override;

  public:
    TcpServer() {}
    virtual ~TcpServer() {}
};

#endif
