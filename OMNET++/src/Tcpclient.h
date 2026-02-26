#ifndef __SOCKETCLIENT_TCPCLIENT_H_
#define __SOCKETCLIENT_TCPCLIENT_H_

#include <omnetpp.h>

using namespace omnetpp;

// Forward declaration del DroneController
class DroneController;

class TcpClient : public cSimpleModule
{
  protected:
    virtual void initialize() override;
    virtual void handleMessage(cMessage *msg) override;
    virtual void finish() override;

  private:
    DroneController* findDroneController();

  public:
      void sendToServer(const std::string& data);
};

#endif
