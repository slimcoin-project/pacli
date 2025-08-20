from decimal import Decimal
from typing import Union

from pypeerassets.exceptions import RecieverAmountMismatch
from pypeerassets.networks import net_query
from pypeerassets.transactions import (tx_output,
                                       p2pkh_script,
                                       nulldata_script,
                                       make_raw_transaction,
                                       Locktime)

from pacli.provider import provider
from pacli.config import Settings
from pacli.utils import sign_transaction, sendtx
from pacli.extended_utils import finalize_tx


class Coin:

    """Commands to create coin transactions."""

    def sendto(self, address: Union[str], amount: Union[float],
               locktime: int=0) -> str:
        '''Send coins from the current main address to another address(es).

        Usage:

            pacli coin sendto [ADDRESS1, ADDRESS2 ...] [AMOUNT1, AMOUNT2 ...]

        Brackets are mandatory even if there is only one address and amount.
        Number of addresses and amounts must match.

        Args:

            locktime: Specify a lock time.'''

        if not len(address) == len(amount):
            raise RecieverAmountMismatch

        network_params = net_query(Settings.network)

        amount_sum = sum(amount)
        inputs = provider.select_inputs(Settings.key.address, amount_sum)

        outs = []

        for addr, index, amount in zip(address, range(len(address)), amount):
            outs.append(
                tx_output(network=Settings.network, value=Decimal(amount),
                          n=index,
                          script=p2pkh_script(address=addr,
                                              network=Settings.network))
            )

        #  first round of txn making is done by presuming minimal fee
        change_sum = Decimal(inputs['total'] - amount_sum - network_params.min_tx_fee)

        outs.append(
            tx_output(network=provider.network,
                      value=change_sum, n=len(outs)+1,
                      script=p2pkh_script(address=Settings.key.address,
                                          network=provider.network))
            )

        unsigned_tx = make_raw_transaction(network=provider.network,
                                           inputs=inputs['utxos'],
                                           outputs=outs,
                                           locktime=Locktime(locktime)
                                           )

        #signedtx = sign_transaction(provider, unsigned_tx, Settings.key)
        finalize_tx(unsigned_tx, sign=True, send=True) # allows sending from P2PK and other inputs

        # return sendtx(signedtx)

    def opreturn(self, string: hex, locktime: int=0) -> str:
        '''send op_return transaction'''

        network_params = net_query(Settings.network)

        inputs = provider.select_inputs(Settings.key.address, 0.01)

        outs = [tx_output(network=provider.network,
                          value=Decimal(0), n=1,
                          script=nulldata_script(bytes.fromhex(string))
                          )
                ]

        #  first round of txn making is done by presuming minimal fee
        change_sum = Decimal(inputs['total'] - network_params.min_tx_fee)

        outs.append(
            tx_output(network=provider.network,
                      value=change_sum, n=len(outs)+1,
                      script=p2pkh_script(address=Settings.key.address,
                                          network=provider.network))
                    )

        unsigned_tx = make_raw_transaction(network=provider.network,
                                           inputs=inputs['utxos'],
                                           outputs=outs,
                                           locktime=Locktime(locktime)
                                           )

        signedtx = sign_transaction(provider, unsigned_tx, Settings.key)

        return sendtx(signedtx)
