#ifndef __DRONECONTROLLER_H_
#define __DRONECONTROLLER_H_

#include <omnetpp.h>
#include <string>
#include <queue>
#include <mutex>

using namespace omnetpp;

class DroneController : public cSimpleModule
{
  protected:
    cMessage *checkMsg = nullptr;
    double checkInterval;

    std::queue<std::string> pendingCommands;
    std::mutex cmdMutex;

  protected:
    virtual void initialize() override;
    virtual void handleMessage(cMessage *msg) override;
    virtual void finish() override;

  public:
    void enqueueCommand(const std::string& jsonCmd);

  private:
    void processCommand(const std::string& jsonCmd);
    void applyMove(int gnbIndex, double x, double y, double z, double speed);
};

#endif
