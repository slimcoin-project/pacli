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
from pacli.extended_utils import finalize_tx, min_amount
from pacli.extended_interface import run_command, PacliDataError
from pacli.keystore_extended import get_main_address


class Coin:

    """Commands to create coin transactions."""

    def sendto(self, address: Union[str], amount: Union[float],
               locktime: int=0) -> str:
        '''Send coins from the current main address to another address(es).

        Usage:

            pacli coin sendto ADDRESS AMOUNT
            pacli coin sendto "[ADDRESS1, ADDRESS2 ...]" "[AMOUNT1, AMOUNT2 ...]"

        Brackets and quotation marks are mandatory if there is more than one address or amount.
        Number of addresses and amounts must match.

        Args:

            locktime: Specify a lock time.'''

        return run_command(self.__sendto, address, amount, locktime=locktime)

    def __sendto(self, address: Union[str], amount: Union[float],
               locktime: int=0) -> str:

        # make simple entering of int and str values without list possible
        if type(amount) in (str, int, float):
            amount = [amount]
        if type(address) == str:
            address = [address]

        if not len(address) == len(amount):
            raise RecieverAmountMismatch

        network_params = net_query(Settings.network)

        amount_sum = sum([Decimal(str(a)) for a in amount])
        main_address = get_main_address()
        inputs = provider.select_inputs(main_address, amount_sum + network_params.min_tx_fee)

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

        min_change_sum = min_amount("output_value")

        if change_sum >= min_change_sum:
            outs.append(
                tx_output(network=provider.network,
                          value=change_sum, n=len(outs)+1,
                          script=p2pkh_script(address=main_address,
                                              network=provider.network))
                )

        unsigned_tx = make_raw_transaction(network=provider.network,
                                           inputs=inputs['utxos'],
                                           outputs=outs,
                                           locktime=Locktime(locktime)
                                           )

        finalize_tx(unsigned_tx, sign=True, send=True) # allows sending from P2PK and other inputs

    def opreturn(self, string: hex, locktime: int=0, ascii: bool=False) -> str:
        '''Send OP_RETURN transaction from the current main address.

        Usage:

            pacli coin opreturn HEX_STRING
            pacli coin opreturn ASCII_STRING -a

        The string must be a valid number of hexadecimal bytes or a valid Python ASCII string if the -a mode is used.

        Args:

            ascii: Enter the string as an ASCII string instead of a hex representation.
            locktime: Specify a lock time.'''

        return run_command(self.__opreturn, string, locktime, ascii=ascii, debug=True)

    def __opreturn(self, string: hex, locktime: int=0, ascii: bool=False, debug: bool=False) -> str:

        network_params = net_query(Settings.network)

        op_return_fee = min_amount("op_return_value")
        min_change_sum = min_amount("output_value")


        total_fees = op_return_fee + network_params.min_tx_fee

        main_address = get_main_address()
        inputs = provider.select_inputs(main_address, total_fees)

        try:
            if ascii is True:
                op_return_script = nulldata_script(string.encode("ascii"))
            else:
                op_return_script = nulldata_script(bytes.fromhex(str(string)))
        except ValueError:
            raise PacliDataError("String contains invalid characters.")

        outs = [tx_output(network=provider.network,
                          value=Decimal(op_return_fee), n=1,
                          script=op_return_script
                          )
                ]

        #  first round of txn making is done by presuming minimal fee
        change_sum = Decimal(inputs['total'] - total_fees)

        if change_sum >= min_change_sum:

            outs.append(
                tx_output(network=provider.network,
                          value=change_sum, n=len(outs)+1,
                          script=p2pkh_script(address=main_address,
                                              network=provider.network))
                        )

        unsigned_tx = make_raw_transaction(network=provider.network,
                                           inputs=inputs['utxos'],
                                           outputs=outs,
                                           locktime=Locktime(locktime)
                                           )

        finalize_tx(unsigned_tx, sign=True, send=True) # allows sending from P2PK and other inputs
