# base level transaction utilities without dependencies on other pacli tools (except provider and config)

from prettyprinter import cpprint as pprint
from pypeerassets.transactions import sign_transaction
import pypeerassets.at.dt_misc_utils as dmu # TODO: refactor this, the "sign" functions could go into the TransactionDraft module.
import pacli.extended.utils as eu
import pacli.extended.config as ce
import pacli.extended.interface as ei
import pacli.extended.keystore as ke
import pacli.extended.handling as eh
from pacli.provider import provider
from pacli.config import Settings
from pacli.utils import (sendtx, cointoolkit_verify)

def check_receiver(tx: dict, receiver: str):
    receivers = []
    for o in tx["vout"]:
        try:
            receivers.append(o["scriptPubKey"]["addresses"][0])
        except (KeyError, IndexError):
            continue # case OP_RETURN etc.

    return receiver in receivers

def check_address_in_txstruct(tx: dict, address: str=None, sender: str=None, firstsender: str=None, receiver: str=None, debug: bool=False) -> bool:
    # Note: address means an OR relation normally (i.e. address can be sender OR receiver).
    # If an AND relation is needed, sender and receiver can be set to the same address.
    # firstsender is for AT txes, where only the first input is credited.

    senders = [s for i in tx["inputs"] for s in i["sender"]]
    receivers = [r for o in tx["outputs"] for r in o["receivers"]]

    if firstsender is not None:
        if len(senders) == 0 or senders[0] != firstsender:
            return False
    if (sender is not None) and (sender not in senders):
        return False
    if (receiver is not None) and (receiver not in receivers):
        return False
    if (address is not None) and (address not in senders + receivers):
        return False
    return True


def return_tx_format(fmt: str, txjson: dict=None, txstruct: dict=None, tracked_address: str=None, debug: bool=False) -> dict:
    # should contain common tx formats except the getrawtransaction TXJSON and the txstruct.

    if fmt == "gatewaytx" and txstruct is not None: # support for txjson probably not needed here
        outputs_to_tracked, oindices = [], []
        for oindex, o in enumerate(txstruct["outputs"]):
            if (o.get("receivers") is not None and tracked_address in o["receivers"]):
                outputs_to_tracked.append(o)
                oindices.append(oindex)

        if outputs_to_tracked:
            tracked_value = sum([o["value"] for o in outputs_to_tracked])
            # sender = senders[0] if len(senders) > 0 else "COINBASE" # fix for coinbase txes
            # result = {"sender" : sender, "outputs" : outputs, "blockheight" : height, "oindices": oindices, "ovalue" : tracked_value}
        else:
            return None


        result = {"txid" : txstruct["txid"],
                  "value" : tracked_value, # txstruct["ovalue"],
                  "outputs" : oindices, # txstruct["oindices"],
                  "blockheight" : txstruct["blockheight"]}

    return result


def extract_txids_from_utxodict(txdicts: list, exclude_cats: list=[], required_address: str=None, debug: bool=False):
    # Processes listtransactions output.
    processed_txids = []
    for txdict in txdicts:
        try:
            assert txdict["txid"] not in processed_txids

            for cat in exclude_cats:
                assert txdict["category"] != cat

            if required_address is not None:
                assert txdict["address"] == required_address

        except (AssertionError, KeyError):
            continue

        processed_txids.append(txdict["txid"])
        yield txdict["txid"]

def set_change_address(change: str=None, debug: bool=False) -> None:

    if change is not None:
        Settings.change = change
        return

    change_address = generate_new_change_address(debug=debug)
    Settings.change = change_address


def check_paclichange_account(debug: bool=False) -> None:
    if "paclichange" not in provider.listaccounts():
        new_address = provider.getnewaddress()
        provider.setaccount(new_address, "paclichange")

def generate_new_change_address(debug: bool=False, alt_address: str=None) -> str:

    try:
        assert ce.show("change_policy", "change_policy") == "newaddress"
        check_paclichange_account(debug=debug)
        change_address = provider.getnewaddress("paclichange")
        if debug:
            print("New change address generated:", change_address)
        return change_address
    except (AttributeError, AssertionError):
        # legacy setting
        if alt_address:
            return alt_address
        else:
            return ke.get_main_address()

def check_if_spent(txid: str, vout: int, address: str=None, minconf: int=1):
    # this only shows if an utxo on an OWN address has been spent
    all_utxos = provider.listunspent(address=address, minconf=minconf)
    utxo_list = [(u["txid"], u["vout"]) for u in all_utxos]
    if (txid, vout) in utxo_list:
         return False
    else:
         return True


def finalize_tx(rawtx: dict,
                verify: bool=False,
                sign: bool=False,
                send: bool=False,
                confirm: bool=False,
                redeem_script: str=None,
                label: str=None,
                key: str=None,
                input_types: list=None,
                ignore_checkpoint: bool=False,
                save: bool=False,
                quiet: bool=False,
                debug: bool=False) -> object:
    """Final steps of a transaction creation. Checks, verifies, signs and sends the transaction, and waits for confirmation if the 'confirm' option is used."""
    # Important function called by all AT, DT and Dex transactions and groups several checks and the last steps (signing) together.


    if sign or send:
        main_address = key.address if key is not None else ke.get_main_address()
        if not quiet and not eu.is_mine(main_address):
            print("Warning: The address you attempt to sign the transaction with is not part of your current wallet.")
            print("This can lead to problems when signing some kinds of transactions and can make them invalid.")

    if verify:
        if Settings.network in ("ppc", "tppc"):

            print(
                cointoolkit_verify(rawtx.hexlify())
                 )  # link to cointoolkit - verify

        else:
            raise eh.PacliInputDataError("Verifying by Cointoolkit is not possible on other chains than Peercoin.")

    if (send == False) and (not quiet):
        ei.print_orange("NOTE: This is a dry run. Your transaction hasn't been broadcasted. To actually broadcast it add the -s flag at the end of the command you've just run.")

    dict_key = 'hex' # key of dict returned to the user.

    if not ignore_checkpoint and (send is True):
        # if a reorg/orphaned checkpoint is detected, require confirmation to continue.
        from pacli.extended.checkpoints import reorg_check, store_checkpoint
        if reorg_check(quiet=quiet):
            raise eh.PacliInputDataError("Reorg check failed. If you want to create the transaction anyway, use the command's --force / --ignore_warnings options if available.")

        store_checkpoint(quiet=quiet)

    if sign:

        if redeem_script is not None:
            if debug: print("Signing with redeem script:", redeem_script)
            # TODO: in theory we need to solve inputs from --new_inputs separately from the p2sh inputs.
            # For now we can only use new_inputs OR spend the P2sh.
            # MODIF: no more the option to use a different key!
            try:
                tx = dmu.sign_p2sh_transaction(provider, rawtx, redeem_script, Settings.key)
            except NameError:
                raise eh.PacliInputDataError("Invalid redeem script.")

        elif (key is not None) or (label is not None): # sign with a different key
            tx = signtx_by_key(rawtx, label=label, key=key)
            # we need to check the type of the input, as the Kutil method cannot sign P2PK
            # TODO: do we really want to preserve this option? Re-check DEX
        else:
            if input_types is None:
                input_types = eu.get_input_types(rawtx)

            if "pubkey" not in input_types:
                tx = sign_transaction(provider, rawtx, Settings.key)
            else:
                tx = dmu.sign_mixed_transaction(provider, rawtx, Settings.key, input_types)

        if send:
            txid = sendtx(tx)
            if not quiet:
                pprint({'txid': txid})

            if confirm:
                eh.confirm_tx(tx, quiet=quiet)

        tx_hex = tx.hexlify()

    elif send:
        # rawtx variable contains an already signed tx (DEX use case)
        txid = sendtx(rawtx)
        if not quiet:
            pprint({'txid': txid })
        else:
            sendtx(rawtx)
        tx_hex = rawtx.hexlify()

        if confirm:
            eh.confirm_tx(rawtx, quiet=quiet)

    else:
        dict_key = 'raw hex'
        tx_hex = rawtx.hexlify()

    if save:
        try:
            assert True in (sign, send) # even if an unsigned tx gets a txid, it doesn't make sense to save it
            txid = tx["txid"] if tx is not None else rawtx["txid"]
        except (KeyError, AssertionError):
            raise eh.PacliInputDataError("You can't save a transaction which was not at least partly signed.")
        else:
            eu.save_transaction(txid, tx_hex)

    if send and not quiet:
        txjson = rawtx.to_json()
        if "locktime" in txjson and int(txjson["locktime"]) > provider.getblockcount():
            ei.print_orange("This transaction has a locktime value of {}.".format(txjson["locktime"]))
            print("Hex string to resubmit the transaction if the client doesn't broadcast it:")
            print(tx_hex)
        elif not eu.check_tx_acceptance(txid=txid, tx_hex=tx_hex):

            ei.print_red("Error: Transaction was not accepted by the client.")
            print("The reason may be that you tried to create a transaction where an input was already spent by another transaction.")
            print("You can try to find out if this is the case with an UTXO check with the following command:\n")
            print("   pacli transaction show {} -u".format(tx_hex))
            print("\nIt will check if the UTXOs used in this transaction were already spent. It accepts also the -a flag to find transactions carried out from change addresses.")
            print("The UTXO check will only work if the address it received is in your wallet.")
            print("This may also be a false negative and the transaction was actually accepted. This can happen if two transactions are broadcast in very fast sequence. It is recommended to wait at least 5 seconds between transaction-related pacli commands.\n")
        else:

            print("Note: Balances called with 'address balance' and 'address list' commands may not update even after the first confirmation.")
            print("In this case, restart your {} client.".format(Settings.network.upper()))

    return { dict_key : tx_hex }


def signtx_by_key(rawtx, label=None, key=None):
    """Allows to sign a transaction with a different than the main key."""

    if not key:
        try:
           key = ke.get_key(label)
        except ValueError:
           raise eh.PacliInputDataError("No key nor label provided.")

    return sign_transaction(provider, rawtx, key)

