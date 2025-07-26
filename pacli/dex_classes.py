import pacli.dex_utils as dxu
import pacli.blockexp_utils as bxu
import pacli.extended_interface as ei
import pacli.extended_utils as eu
import pypeerassets as pa
import pacli.extended_commands as ec
import pacli.config_extended as ce
from decimal import Decimal
from prettyprinter import cpprint as pprint
from pacli.provider import provider
from pacli.config import Settings


class Swap:
    """Commands allowing the decentralized exchange of tokens for coins."""

    @classmethod
    def lock(self,
            idstr: str,
            amount: str,
            lock: int,
            lockaddr: str,
            receiver: str=None,
            blockheight: bool=False,
            addrtype: str="p2pkh",
            change: str=Settings.change,
            force: bool=False,
            wait_for_confirmation: bool=False,
            sign: bool=True,
            send: bool=True,
            quiet: bool=False,
            debug: bool=False):
        """Locks a number of tokens on the receiving address.

        Usage:

            pacli swap lock TOKEN TOKEN_AMOUNT LOCK_BLOCKS LOCK_ADDRESS [RECEIVER]

        By default, you specify the number of blocks to lock the tokens; with --blockheight you specify the final block height.
        Transfers are only permitted to the Lock Address. This is the condition to avoid scams in the swap DEX.
        Card default receiver is the sender (the current main address).

        Args:

          sign: Sign the transaction.
          send: Send the transaction.
          blockheight: Lock to an absolute block height (instead of a relative number of blocks).
          receiver: Specify another receiver (can be only one)
          addrtype: Address type (default: p2pkh)
          change: Specify a custom change address.
          wait_for_confirmation: Wait for the first confirmation of the transaction and display a message.
          force: Create transaction even if the reorg check fails. Does not check balance (faster, but use with caution).
          quiet: Output only the transaction in hexstring format (script-friendly).
          debug: Show additional debug information.
         """

        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", idstr, quiet=quiet, debug=debug)
        change_address = ec.process_address(change, debug=debug)
        lock_address = ec.process_address(lockaddr, debug=debug)
        if receiver is None:
            receiver_address = Settings.key.address
        else:
            receiver_address = ec.process_address(receiver)
        return ei.run_command(dxu.card_lock, deckid=deckid, amount=str(amount), lock=lock, lockaddr=lock_address, addrtype=addrtype, absolute=blockheight, change=change_address, receiver=receiver_address, sign=sign, send=send, force=force, confirm=wait_for_confirmation, txhex=quiet, debug=debug)

    @classmethod
    def create(self,
                 token: str,
                 partner_address: str,
                 partner_input: str,
                 card_amount: str,
                 coin_amount: str,
                 coinseller_change_address: str=None,
                 label: str=None,
                 quiet: bool=False,
                 sign: bool=True,
                 debug: bool=False):
        """Creates a new exchange transaction, signs it partially and outputs it in hex format to be submitted to the exchange partner.

        Usage:

            pacli swap create DECK PARTNER_ADDRESS PARTNER_INPUT TOKEN_AMOUNT COIN_AMOUNT

        PARTNER_ADDRESS and PARTNER_INPUT come from your exchange partner (see manual).
        NOTE: To pay the transaction fees, you need coins on your address which don't come directly from mining (coinbase inputs can't be used due to an upstream bug). It will work if you transfer mined coins in a regular transaction to the address you will be using for the swap.

        Args:

          sign: Sign the transaction.
          coinseller_change_address: Specify a change address of the coin seller (default: sender address)
          label: Specify a label to save the transaction hex string with.
          quiet: Suppress output.
          debug: Show additional debug information.
        """

        partner_address = ei.run_command(ec.process_address, partner_address, debug=debug)
        coinseller_change_address = ei.run_command(ec.process_address, coinseller_change_address, debug=debug) if coinseller_change_address is not None else None
        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", token, quiet=quiet)
        return ei.run_command(dxu.build_coin2card_exchange, deckid, partner_address, partner_input, Decimal(str(card_amount)), Decimal(str(coin_amount)), sign=sign, coinseller_change_address=coinseller_change_address, save_identifier=label, debug=debug)

    @classmethod
    def finalize(self, txstr: str, send: bool=True, force: bool=False, wait_for_confirmation: bool=False, txhex: bool=False, quiet: bool=False, debug: bool=False):
        """Signs and broadcasts an exchange transaction.

        Usage:

            pacli swap finalize TX_HEXSTRING

        TX_HEXSTRING is the partially signed transaction as an hex string.

        Args:

          send: Sends the transaction
          wait_for_confirmation: Waits for the transaction to confirm.
          force: Creates the transaction even if the reorg check fails (use with caution!).
          txhex: Shows only the hex string of the transaction.
          quiet: Suppresses some printouts.
          debug: Show additional debug information.
        """
        return ei.run_command(dxu.finalize_coin2card_exchange, txstr, send=send, force=force, confirm=wait_for_confirmation, quiet=quiet, txhex=txhex, debug=debug)

    @classmethod
    def list_locks(self, idstr: str, blockheight: int=None, quiet: bool=False, debug: bool=False):
        """Shows all current locks of a deck.

        Usage:

            pacli swap list_locks DECK

        Args:

          blockheight: Specify a block height to show locks at (BUGGY). To be used as a positional argument (flag name not necessary).
          quiet: Don't prettyprint the lock dictionary and suppress additional output.
          debug: Show debug information.
        """
        # TODO: blockheight seems not to work.

        blockheight = provider.getblockcount() if blockheight is None else blockheight
        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", idstr, quiet=quiet)
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
        cards = pa.find_all_valid_cards(dxu.provider, deck)
        state = pa.protocol.DeckState(cards, cleanup_height=blockheight, debug=debug)

        if quiet is True:
            return state.locks
        else:
            return dxu.prettyprint_locks(state.locks, blockheight, decimals=deck.number_of_decimals)

    @classmethod
    def select_coins(self, amount, address=Settings.key.address, utxo_type="pubkeyhash", debug: bool=False):
        """Prints out all suitable utxos for an exchange transaction.

        Usage:

            pacli swap select_coins AMOUNT [ADDRESS]

        If ADDRESS is not given, the current main address is used.
        NOTE: due to an upstream bug, coinbase UTXOs can't be used for swaps. They will be ignored.

        Args:

          address: Alternative address to show suitable UTXOs. To be used as a positional argument (flag name not necessary).
          utxo_type: Specify a different UTXO type (default: pubkeyhash)
          debug: Show additional debug information.
        """

        addr = ei.run_command(ec.process_address, address, debug=debug)
        return ei.run_command(dxu.select_utxos, minvalue=amount, address=addr, utxo_type=utxo_type, debug=debug)

    # @classmethod
    def check(self, _txstring: str, coinseller_change_address: str=None, token_receiver_address: str=None, amount: str=None, debug: bool=False):
        """Checks a swap transaction, allowing the token buyer to see if everything is correct.

        Usage:

            pacli swap check TRANSACTION

        TRANSACTION can be either the raw transactions' hex string (TXHEX) or the label of a stored transaction.
        If no more arguments are given, the transaction's inputs and outputs will be shown.

        Args:

          token_receiver_address: The address provided by the token buyer to receive the coins.
          coinseller_change_address: The (optional) address provided by the token buyer to receive the change.
          amount: Amount of coins provided to buy the tokens.
          debug: Show additional debug information.
        """

        kwargs = locals()
        del kwargs["self"]
        ei.run_command(self.__check, **kwargs)

    def __check(self, _txstring: str, coinseller_change_address: str=None, token_receiver_address: str=None, amount: str=None, debug: bool=False):

        txhex = ce.show("transaction", _txstring, quiet=True)
        if txhex is None:
            txhex = _txstring
        try:
            txjson = provider.decoderawtransaction(txhex)
            txstruct = bxu.get_tx_structure(tx=txjson, ignore_blockhash=True)
        except:
            raise ei.PacliInputDataError("No valid transaction hex string or label provided.")

        # {'inputs': [{'sender': ['mx2tsUDBH4wVUrgdGcPuiHz9YVeJKj7PMz'], 'value': 0.01}, {'sender': ['mwzox84gMy8TKdeBftrfpmwGVZnJJdaReg'], 'value': 100.0}], 'outputs': [{'receivers': ['mkwJijAwqXNFcEBxuC93j3Kni43wzXVuik'], 'value': 0.01}, {'receivers': [], 'value': 0.01}, {'receivers': ['mzT2eco8dPUYbT765zRALjNDKQGGNogRYW'], 'value': 0.01}, {'receivers': ['mx2tsUDBH4wVUrgdGcPuiHz9YVeJKj7PMz'], 'value': 10.0}, {'receivers': ['mx2tsUDBH4wVUrgdGcPuiHz9YVeJKj7PMz'], 'value': 0.01}, {'receivers': ['mzT2eco8dPUYbT765zRALjNDKQGGNogRYW'], 'value': 89.96}]}


        pprint("Senders and receivers of the swap transaction:")
        pprint(txstruct)
        try:
            # Note: outputs 2 and 4 go to the token seller, so they aren't checked here in detail.
            token_seller = txstruct["inputs"][0]["sender"][0]
            token_buyer = txstruct["inputs"][1]["sender"][0]
            amount_provided = Decimal(str(txstruct["inputs"][1]["value"]))
            token_receiver = txstruct["outputs"][3]["receivers"][0]
            coin_receiver = txstruct["outputs"][3]["receivers"][0]
            change_receiver = txstruct["outputs"][5]["receivers"][0]
            change_returned = Decimal(str(txstruct["outputs"][5]["value"]))
            all_inputs = sum([Decimal(str(i["value"])) for i in txstruct["inputs"]])
            all_outputs = sum([Decimal(str(o["value"])) for o in txstruct["outputs"]])
            tx_fee = all_inputs - all_outputs
            p2th_fee = Decimal(str(txstruct["outputs"][0]["value"]))
            op_return_fee = Decimal(str(txstruct["outputs"][1]["value"]))
            card_transfer_fee = Decimal(str(txstruct["outputs"][2]["value"]))
            all_fees = tx_fee + p2th_fee + op_return_fee + card_transfer_fee
        except (KeyError, IndexError):
            raise ei.PacliDataError("Incorrect transaction structure. Don't proceed with the transaction.")

        pprint("Token seller's address: {}".format(token_seller))
        pprint("Token buyer's address: {}".format(token_buyer))
        pprint("Token receiver's address: {}".format(token_receiver))
        if token_receiver != token_buyer:
            print("WARNING: The token receiver is different than the address providing the coins for the exchange.")
            print("This may be intentionally set up by the token buyer, but can also be a manipulation from the token seller's part.")
            print("If you are the token buyer, check carefully that both addresses belong to you.")
        if token_receiver_address and (token_receiver != token_receiver_address):
            ei.print_red("CHECK FAILED: The token receiver address you provided in this check isn't the address receiving the tokens in the swap transaction.")
        pprint("Change receiver's address: {}".format(change_receiver))
        pprint("Change returned: {}".format(change_returned))
        if coinseller_change_address and (change_receiver != coinseller_change_address):
            ei.print_red("CHECK FAILED: The change receiver address you provided in this check isn't the address receiving the change coins in the swap transaction.")
        pprint("Fees paid: {}".format(all_fees))
        paid_amount = amount_provided - change_returned - all_fees
        pprint("Amount paid for the tokens (not including fees): {}".format(paid_amount))
        if amount is not None:
            intended_amount = Decimal(str(amount))
            if intended_amount < paid_amount:
                ei.print_red("CHECK FAILED: The token buyer didn't receive all the change or will pay more than expected.")
                ei.print_red("Missing amount: {}.".format(paid_amount - intended_amount))

        print("If any check failed, it is advised to the token buyer to abandon the swap.")

