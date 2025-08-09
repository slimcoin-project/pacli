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
                 amount_cards: str,
                 amount_coins: str,
                 buyer_change_address: str=None,
                 label: str=None,
                 quiet: bool=False,
                 sign: bool=True,
                 debug: bool=False):
        """Creates a new exchange transaction, signs it partially and outputs it in hex format to be submitted to the exchange partner.

        Usage:

            pacli swap create DECK PARTNER_ADDRESS PARTNER_INPUT TOKEN_AMOUNT COIN_AMOUNT

        PARTNER_ADDRESS and PARTNER_INPUT come from your exchange partner (see manual). PARTNER_ADDRESS can be an address or a label of a stored address.
        NOTE: To pay the transaction fees, you need coins on your address which don't come directly from mining (coinbase inputs can't be used due to an upstream bug). It will work if you transfer mined coins in a regular transaction to the address you will be using for the swap.

        Args:

          sign: Sign the transaction.
          buyer_change_address: Specify a change address of the token buyer (default: sender address). Can be the address itself or a label of a stored address.
          label: Specify a label to save the transaction hex string with.
          quiet: Suppress output.
          debug: Show additional debug information.
        """

        partner_address = ei.run_command(ec.process_address, partner_address, debug=debug)
        buyer_change_address = ei.run_command(ec.process_address, buyer_change_address, debug=debug) if coinseller_change_address is not None else None
        deckid = ei.run_command(eu.search_for_stored_tx_label, "deck", token, quiet=quiet)
        return ei.run_command(dxu.build_coin2card_exchange, deckid, partner_address, partner_input, Decimal(str(amount_cards)), Decimal(str(amount_coins)), sign=sign, coinseller_change_address=buyer_change_address, save_identifier=label, debug=debug)

    # @classmethod
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

        kwargs = locals()
        del kwargs["self"]
        return ei.run_command(self.__finalize, **kwargs)

    def __finalize(self, txstr: str, send: bool=True, force: bool=False, wait_for_confirmation: bool=False, txhex: bool=False, quiet: bool=False, debug: bool=False):

        txhexstr = ce.show("transaction", txstr, quiet=True)
        if txhexstr is None:
            txhexstr = txstr

        if not force:
            fail = ei.run_command(self.__check, txhexstr, return_state=True, debug=debug)
            if fail is True:
                raise ei.PacliDataError("Swap check failed. It is advised to not proceed with the exchange. If you are sure everything is correct, use --force.")
        return ei.run_command(dxu.finalize_coin2card_exchange, txhexstr, send=send, force=force, confirm=wait_for_confirmation, quiet=quiet, txhex=txhex, debug=debug)

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

    def __check(self, _txstring: str, coinseller_change_address: str=None, token_receiver_address: str=None, amount: str=None, return_state: bool=False, debug: bool=False):

        fail, notmine = False, False
        txhex = ce.show("transaction", _txstring, quiet=True)
        if txhex is None:
            txhex = _txstring
        try:
            txjson = provider.decoderawtransaction(txhex)
            txstruct = bxu.get_tx_structure(tx=txjson, ignore_blockhash=True)
        except:
            raise ei.PacliInputDataError("No valid transaction hex string or label provided.")

        print("Checking swap ...")
        pprint("Senders and receivers of the swap transaction:")
        pprint(txstruct)
        try:
            # Note: outputs 2 and 4 go to the token seller, so they aren't checked here in detail.
            token_seller = txstruct["inputs"][0]["sender"][0]
            token_buyer = txstruct["inputs"][1]["sender"][0]
            amount_provided = Decimal(str(txstruct["inputs"][1]["value"]))
            token_receiver = txstruct["outputs"][3]["receivers"][0]
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
            print("WARNING: The address providing the coins for the swap isn't identic to the address which will receive the tokens.")
            print("This may be intentionally set up by the token buyer for privacy reasons, but can also be a manipulation from the token seller's part.")

        if token_receiver_address is not None and (token_receiver != token_receiver_address):
            ei.print_red("The token receiver address you provided in this check isn't the address receiving the tokens in the swap transaction.")
            fail = True
        pprint("Change receiver's address: {}".format(change_receiver))
        pprint("Change returned: {}".format(change_returned))
        if coinseller_change_address is not None and (change_receiver != coinseller_change_address):
            ei.print_red("The change receiver address you provided in this check isn't the address receiving the change coins in the swap transaction.")
            fail = True
        pprint("Fees paid: {}".format(all_fees))
        paid_amount = amount_provided - change_returned - all_fees
        pprint("Amount paid for the tokens (not including fees): {}".format(paid_amount))
        if amount is not None:
            intended_amount = Decimal(str(amount))
            if intended_amount < paid_amount:
                ei.print_red("The token buyer didn't receive all the change or will pay more than expected.")
                ei.print_red("Missing amount: {}.".format(paid_amount - intended_amount))
                fail = True

        for adr in token_receiver, change_receiver:
            validation = provider.validateaddress(adr)
            if validation.get("ismine") != True:
                notmine = True
                fail = True
        if notmine is True:
            ei.print_red("Ownership check failed: At least one of the addresses which should be under the token buyer's control in this swap (token receiver and change receiver) isn't part of your current wallet.")
            print("This may be intentional if you provided an address of another wallet, or are using this command running the client with a different wallet than the swap's wallet, but can also be a manipulation by the token buyer. Be careful.")
        else:
            print("Ownership check passed: Both the token receiver and the change address for the provided coins are part of your currently used wallet.")
        if return_state is True:
            return fail
        else:
            if fail is True:
                ei.print_red("SWAP CHECK FAILED. If you are the token buyer and see this or any red warning, it is advised to abandon the swap.")
            else:
                print("SWAP CHECK PASSED. If there is a warning, read it carefully to avoid any losses.")
