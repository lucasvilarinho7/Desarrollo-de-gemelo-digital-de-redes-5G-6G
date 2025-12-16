#ifndef __SOCKETCLIENT_TCPCLIENT_H_
#define __SOCKETCLIENT_TCPCLIENT_H_

#include <omnetpp.h>

using namespace omnetpp;


class TcpClient : public cSimpleModule
{
  protected:
    virtual void initialize() override;
    virtual void handleMessage(cMessage *msg) override;
    virtual void finish() override;

  public:
      void sendToServer(const std::string& data);
};

#endif
