import grpc
import time
import sys

import aergo.herapy as herapy


def run(t_anchor, t_final):
    f = open("./bridge_operator/bridge_addresses.txt", "r")
    addr1 = f.readline()[:52]
    addr2 = f.readline()[:52]
    print(t_anchor, t_final)
    f.close()
    try:
        aergo1 = herapy.Aergo()
        aergo2 = herapy.Aergo()

        print("------ Connect AERGO -----------")
        aergo1.connect('localhost:7845')
        aergo2.connect('localhost:8845')

        print("------ Set Sender Account -----------")
        sender_private_key = "6hbRWgddqcg2ZHE5NipM1xgwBDAKqLnCKhGvADWrWE18xAbX8sW"
        sender_account = aergo1.new_account(password="test",
                                            private_key=sender_private_key)
        sender_address = sender_account.address.__str__()
        aergo2.new_account(password="test",
                           private_key=sender_private_key)
        aergo1.get_account()
        aergo2.get_account()
        print("  > Sender Address: {}".format(sender_account.address))
        print("------ START BRIDGE OPERATOR -----------")


        try:
            while True :
                # TODO Support state query in herapy
                # Get current merge block height

                # Get origin and destination best height
                _, best_height1 = aergo1.get_blockchain_status()
                _, best_height2 = aergo2.get_blockchain_status()

                # Waite for best height - t_final >= merge block height + t_anchor

                # Calculate finalised block to broadcast

                # Broadcast finalised merge block

                # Waite t_anchor
                time.sleep(1)
                print("sleep")
        except KeyboardInterrupt:
            print("Shutting down operator")


        print("------ Disconnect AERGO -----------")
        aergo1.disconnect()
        aergo2.disconnect()
    except grpc.RpcError as e:
        print('Get Blockchain Status failed with {0}: {1}'.format(e.code(),
                                                                  e.details()))


if __name__ == '__main__':
    if len(sys.argv) == 3 :
        run(int(sys.argv[1]), int(sys.argv[2]))
    else :
        print("Usage : provide anchoring frequency and finalization time")
