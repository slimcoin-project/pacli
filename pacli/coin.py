from decimal import Decimal
from typing import Union

from pypeerassets.exceptions import RecieverAmountMismatch
from pypeerassets.networks import net_query
from pypeerassets.transactions import (tx_output,
                                       p2pkh_script,
                                       nulldata_script,
                                       make_raw_transaction,
                                       Locktime)
from pypeerassets.legacy import is_legacy_blockchain, legacy_mintx

from pacli.provider import provider
from pacli.config import Settings
from pacli.utils import sign_transaction, sendtx
from pacli.extended_utils import finalize_tx
from pacli.extended_interface import run_command


class Coin:

    """Commands to create coin transactions."""

    def sendto(self, address: Union[str], amount: Union[float],
               locktime: int=0) -> str:
        '''Send coins from the current main address to another address(es).

        Usage:

            pacli coin sendto ADDRESS AMOUNT
            pacli coin sendto [ADDRESS1, ADDRESS2 ...] [AMOUNT1, AMOUNT2 ...]

        Brackets are mandatory if there is more than one address or amount.
        Number of addresses and amounts must match.

        Args:

            locktime: Specify a lock time.'''

        # make simple entering of int and str values without list possible
        if type(amount) in (str, int, float):
            amount = [amount]
        if type(address) == str:
            address = [address]

        if not len(address) == len(amount):
            raise RecieverAmountMismatch

        network_params = net_query(Settings.network)

        amount_sum = sum([Decimal(str(a)) for a in amount])
        inputs = run_command(provider.select_inputs, Settings.key.address, amount_sum)

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

        run_command(finalize_tx, unsigned_tx, sign=True, send=True) # allows sending from P2PK and other inputs

    def opreturn(self, string: hex, locktime: int=0) -> str:
        '''Send OP_RETURN transaction from the current main address.

        Usage:

            pacli coin opreturn STRING

        The STRING must be a valid number of hexadecimal bytes.

        Args:

            locktime: Specify a lock time.'''

        network_params = net_query(Settings.network)

        if is_legacy_blockchain(Settings.network, "nulldata"):
            op_return_fee = legacy_mintx(Settings.network) * Decimal(str(network_params.from_unit))
        else:
            op_return_fee = 0
        total_fees = op_return_fee + network_params.min_tx_fee

        inputs = provider.select_inputs(Settings.key.address, total_fees)

        outs = [tx_output(network=provider.network,
                          value=Decimal(op_return_fee), n=1,
                          script=nulldata_script(bytes.fromhex(str(string)))
                          )
                ]

        #  first round of txn making is done by presuming minimal fee
        change_sum = Decimal(inputs['total'] - total_fees)

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

        #return sendtx(signedtx)
        finalize_tx(unsigned_tx, sign=True, send=True) # allows sending from P2PK and other inputs
