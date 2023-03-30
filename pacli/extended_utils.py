import pypeerassets as pa
from typing import Optional, Union
from pypeerassets.pautils import load_deck_p2th_into_local_node
from pypeerassets.transactions import sign_transaction
from pypeerassets.networks import net_query
from pypeerassets.at.protobuf_utils import serialize_deck_extended_data
from pypeerassets.at.constants import ID_AT, ID_DT
import pypeerassets.at.dt_misc_utils as dmu # TODO: refactor this, the "sign" functions could go into the TransactionDraft module.
from pacli.provider import provider
from pacli.config import Settings


# TODO: workaround for the identification problem, try to make more elegant.
# The problem is that I don't want the constants in __main__. So we'll have to list them here.


# Utils which are used by at and dt (and perhaps normal) tokens.

def create_deckspawn_data(identifier, epoch_length=None, epoch_reward=None, min_vote=None, sdp_periods=None, sdp_deckid=None, at_address=None, multiplier=None, addr_type=2, startblock=None, endblock=None):

    # note: we use an additional identifier only for this function, to avoid having to import extension
    # data into __main__.
    #if identifier in ("at", "dt"):
    #    identifier = identifier.encode("utf-8") # ensure bytes format. Probably not really necessary.

    if identifier == "dt":

        params = {"at_type" : ID_DT,
                 "epoch_length" : int(epoch_length),
                 "epoch_quantity": int(epoch_reward),
                 "min_vote" : int(min_vote),
                 "sdp_deckid" : bytes.fromhex(sdp_deckid) if sdp_deckid else b"",
                 "sdp_periods" : int(sdp_periods) if sdp_periods else 0 }

    elif identifier == "at":

        params = {"at_type" : ID_AT,
                  "multiplier" : int(multiplier),
                  "at_address" : at_address,
                  "addr_type" : int(addr_type),
                  "startblock" : int(startblock),
                  "endblock" : int(endblock)}

    data = serialize_deck_extended_data(net_query(provider.network), params=params)
    # print("OP_RETURN length in bytes:", len(data))
    return data


def list_decks(identifier: str="dt"):
    # quick workaround for the problem that we don't want too much extension stuff in __main__.
    at_type = { "at" : ID_AT, "dt" : ID_DT }
    return dmu.list_decks_by_at_type(provider, at_type[identifier])

def init_deck(network, deckid, rescan=True):
    deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)
    if deckid not in provider.listaccounts():
        provider.importprivkey(deck.p2th_wif, deck.id, rescan)
        print("Importing P2TH address from deck.")
    else:
        print("P2TH address was already imported.")
    check_addr = provider.validateaddress(deck.p2th_address)
    print("Output of validation tool:\n", check_addr)
        # load_deck_p2th_into_local_node(provider, deck) # we don't use this here because it doesn't provide the rescan option

def signtx_by_key(rawtx, label=None, key=None):
    # Allows to sign a transaction with a different than the main key.

    if not key:
        try:
           key = get_key(label)
        except ValueError:
           raise ValueError("No key nor key label provided.")

    return sign_transaction(provider, rawtx, key)

def get_input_types(rawtx):
    # gets the types of ScriptPubKey inputs of a transaction.
    # Not ideal in terms of resource consumption/elegancy, but otherwise we would have to change PeerAssets core code,
    # because it manages input selection (RpcNode.select_inputs)
    input_types = []
    try:
        for inp in rawtx.ins:
            prev_tx = provider.getrawtransaction(inp.txid, 1)
            prev_out = prev_tx["vout"][inp.txout]
            input_types.append(prev_out["scriptPubKey"]["type"])

        return input_types

    except KeyError:
        raise ValueError("Transaction data not correctly given.")


def finalize_tx(rawtx, verify, sign, send, redeem_script=None, label=None, key=None, input_types=None, debug=False):
    # groups the last steps together

    if verify:
        print(
            cointoolkit_verify(rawtx.hexlify())
             )  # link to cointoolkit - verify

    if False in (sign, send):
        print("NOTE: This is a dry run, your transaction will still not be broadcasted.\nAdd --sign --send to the command to broadcast it")

    if sign:

        if redeem_script is not None:
            if debug: print("Signing with redeem script:", redeem_script)
            # TODO: in theory we need to solve inputs from --new_inputs separately from the p2sh inputs.
            # For now we can only use new_inputs OR spend the P2sh.
            # TODO: here we use Settings.key, but give the option to provide different key in donation release command?
            try:
                tx = dmu.sign_p2sh_transaction(provider, rawtx, redeem_script, Settings.key)
            except NameError as e:
                print("Exception:", e)
                #    return None

        elif (key is not None) or (label is not None): # sign with a different key
            tx = signtx_by_key(rawtx, label=label, key=key)
            # we need to check the type of the input, as the Kutil method cannot sign P2PK
        else:
            if input_types is None:
                input_types = get_input_types(rawtx)

            if "pubkey" not in input_types:
                tx = sign_transaction(provider, rawtx, Settings.key)
            else:
                tx = dmu.sign_mixed_transaction(provider, rawtx, Settings.key, input_types)

        if send:
            pprint({'txid': sendtx(tx)})
        return {'hex': tx.hexlify()}

    return rawtx.hexlify()

def get_wallet_transactions(fburntx: bool=False):
    start = 0
    raw_txes = []
    while True:
        new_txes = provider.listtransactions(many=999, since=start, fBurnTx=fburntx) # option fBurnTx=burntxes doesn't work as expected
        raw_txes += new_txes
        if len(new_txes) == 999:
            start += 999
        else:
            break
    return raw_txes

def find_transaction_by_string(searchstring: str, only_start: bool=False):

    wallet_txids = set([tx.txid for tx in get_wallet_transactions()])
    for txid in wallet_txids:
       if (only_start and txid.startswith(searchstring)) or (searchstring in txid and not only_start):
           break
    return txid

def advanced_card_transfer(deckid: str, receiver: list=None, amount: list=None,
                 asset_specific_data: str=None, locktime: int=0, verify: bool=False,
                 sign: bool=False, send: bool=False) -> Optional[dict]:
    # allows some more options, and to use P2PK inputs.

    deck = pa.find_deck(deckid)

    if isinstance(deck, pa.Deck):
        card = pa.CardTransfer(deck=deck,
                               receiver=receiver,
                               amount=[self.to_exponent(deck.number_of_decimals, i)
                                       for i in amount],
                               version=deck.version,
                               asset_specific_data=asset_specific_data
                               )

    else:

        raise Exception({"error": "Deck {deckid} not found.".format(deckid=deckid)})

    issue_tx = pa.card_transfer(provider=provider,
                                 inputs=provider.select_inputs(Settings.key.address, 0.02),
                                 card=card,
                                 change_address=Settings.change,
                                 locktime=locktime
                                 )

    return finalize_tx(issue_tx, verify, sign, send)
