import grpc
import time

import aergo.herapy as herapy


def run():
    f = open("./contracts/bytecode.txt", "r")
    payload_str = f.read()[:-1]
    f.close()
    payload = herapy.utils.decode_address(payload_str)
    print("------ DEPLOY BRIDGE BETWEEN CHAIN1 & CHAIN2 -----------")
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

        print("------ Deploy SC -----------")
        tx1, result1 = aergo1.deploy_sc(amount=0,
                                        payload=payload,
                                        args=[sender_address])
        tx2, result2 = aergo2.deploy_sc(amount=0,
                                        payload=payload,
                                        args=[sender_address])
        print("{}".format(herapy.utils.convert_tx_to_json(tx1)))
        print("{}".format(herapy.utils.convert_tx_to_json(tx2)))
        if result1.status != herapy.CommitStatus.TX_OK:
            print("    > ERROR[{0}]: {1}".format(result1.status, result1.detail))
            aergo.disconnect()
            return
        else:
            print("    > result[{0}] : {1}".format(result1.tx_id, result1.status.name))
            print(herapy.utils.convert_bytes_to_int_str(bytes(tx1.tx_hash)))
        if result2.status != herapy.CommitStatus.TX_OK:
            print("    > ERROR[{0}]: {1}".format(result2.status, result2.detail))
            aergo.disconnect()
            return
        else:
            print("    > result[{0}] : {1}".format(result2.tx_id, result2.status.name))
            print(herapy.utils.convert_bytes_to_int_str(bytes(tx2.tx_hash)))

        time.sleep(3)

        print("------ Check deployment of SC -----------")
        result1 = aergo1.get_tx_result(tx1.tx_hash)
        if result1.status != herapy.SmartcontractStatus.CREATED:
            print("  > ERROR[{0}]:{1}: {2}".format(
                result1.contract_address, result1.status, result1.detail))
            aergo.disconnect()
            return
        result2 = aergo2.get_tx_result(tx2.tx_hash)
        if result2.status != herapy.SmartcontractStatus.CREATED:
            print("  > ERROR[{0}]:{1}: {2}".format(
                result2.contract_address, result2.status, result2.detail))
            aergo.disconnect()
            return

        sc_address1 = result1.contract_address
        sc_address2 = result2.contract_address

        print("  > SC Address ORIGIN: {}".format(sc_address1))
        print("  > SC Address DESTINATION: {}".format(sc_address2))


        print("------ Store addresses in bridge_addresses.txt -----------")
        f = open("./bridge_operator/bridge_addresses.txt", "w")
        f.write(sc_address1)
        f.write("_ADDR_1\n")
        f.write(sc_address2)
        f.write("_ADDR_2")
        f.close()

        print("------ Disconnect AERGO -----------")
        aergo1.disconnect()
        aergo2.disconnect()
    except grpc.RpcError as e:
        print('Get Blockchain Status failed with {0}: {1}'.format(e.code(),
                                                                  e.details()))


if __name__ == '__main__':
    run()
