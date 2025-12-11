import time, re, sys, hashlib
from decimal import Decimal
import pypeerassets as pa
from typing import Optional, Union
from prettyprinter import cpprint as pprint
from btcpy.structs.address import InvalidAddress
from pypeerassets.transactions import sign_transaction, NulldataScript
from pypeerassets.networks import net_query
from pypeerassets.pa_constants import param_query
from pypeerassets.at.protobuf_utils import serialize_deck_extended_data
from pypeerassets.at.constants import ID_AT, ID_DT
from pypeerassets.pautils import amount_to_exponent, exponent_to_amount, parse_card_transfer_metainfo, read_tx_opreturn
from pypeerassets.exceptions import InsufficientFunds
from pypeerassets.__main__ import get_card_transfer
from pypeerassets.legacy import is_legacy_blockchain, legacy_mintx
import pypeerassets.at.dt_misc_utils as dmu # TODO: refactor this, the "sign" functions could go into the TransactionDraft module.
import pacli.extended_config as ce
import pacli.extended_interface as ei
import pacli.extended_keystore as ke
import pacli.extended_token_queries as etq
from pacli.provider import provider
from pacli.config import Settings
from pacli.utils import (sendtx, cointoolkit_verify)


def advanced_card_transfer(deck: object=None, deckid: str=None, receiver: list=None, amount: list=None,
                 asset_specific_data: str=None, locktime: int=0, verify: bool=False, change: str=None,
                 card_locktime: str=None, card_lockhash: str=None, card_lockhash_type: str=None,
                 sign: bool=False, send: bool=False, balance_check: bool=False, force: bool=False, quiet: bool=False, confirm: bool=False, debug: bool=False) -> Optional[dict]:
    """Alternative function for card transfers. Allows some more options than the vanilla PeerAssets features, and to use P2PK inputs."""
    # TODO: recheck where the vanilla function sends the change
    # TODO: recheck if balance check checks for locked tokens, in this case, it can be used also by dex_utils.card_lock() (normally this should be done in DeckState).

    if not deck:
        deck = pa.find_deck(provider, deckid, Settings.deck_version, Settings.production)

    amount_list = [amount_to_exponent(i, deck.number_of_decimals) for i in amount]
    change_address = Settings.change if change is None else change
    main_address = ke.get_main_address()

    # balance check
    if balance_check:
        if not quiet:
            print("Checking sender balance ...")
        balance = etq.get_address_token_balance(deck, main_address)
        if balance < sum(amount):
            raise ei.PacliInputDataError("Not enough balance of this token.")

    if isinstance(deck, pa.Deck):
        card = pa.CardTransfer(deck=deck,
                               receiver=receiver,
                               amount=amount_list,
                               version=deck.version,
                               asset_specific_data=asset_specific_data,
                               locktime=card_locktime,
                               lockhash=card_lockhash,
                               lockhash_type=card_lockhash_type
                               )

    else:

        raise ei.PacliInputDataError({"error": "Deck {deckid} not found.".format(deckid=deckid)})

    try:
        allfees = calc_cardtransfer_fees(legacyfix=True)
        inputs = provider.select_inputs(main_address, allfees)
        issue_tx = pa.card_transfer(provider=provider,
                                 inputs=inputs,
                                 card=card,
                                 change_address=change_address,
                                 locktime=locktime
                                 )

    except InsufficientFunds:
        raise ei.PacliInputDataError("Insufficient funds. Minimum balance is {} coins.".format(allfees))

    return finalize_tx(issue_tx, verify=verify, sign=sign, send=send, quiet=quiet, ignore_checkpoint=force, confirm=confirm, debug=debug)


def create_deckspawn_data(identifier: str, epoch_length: int=None, epoch_reward: int=None, min_vote: int=None, sdp_periods: int=None, sdp_deckid: str=None, at_address: str=None, multiplier: int=None, addr_type: int=2, startblock: int=None, endblock: int=None, extradata: bytes=None, debug: bool=False) -> str:
    """Creates a Protobuf datastring with the deck metadata."""

    if multiplier is None:
        multiplier = 1
    if (endblock and startblock) and (endblock < startblock):
        raise ei.PacliInputDataError("The end block height has to be at least as high as the start block height.")

    if multiplier % 1 != 0:
        raise ei.PacliInputDataError("The multiplier has to be an integer number.")

    if identifier == ID_DT:

        params = {"at_type" : ID_DT,
                 "epoch_length" : int(epoch_length),
                 "epoch_reward": int(epoch_reward),
                 "min_vote" : int(min_vote) if min_vote else 0,
                 "sdp_deckid" : bytes.fromhex(sdp_deckid) if sdp_deckid else b"",
                 "sdp_periods" : int(sdp_periods) if sdp_periods else 0 }

    elif identifier == ID_AT:

        params = {"at_type" : ID_AT,
                  "multiplier" : int(multiplier),
                  "at_address" : at_address,
                  "addr_type" : int(addr_type),
                  "startblock" : int(startblock) if startblock else 0,
                  "endblock" : int(endblock) if endblock else 0,
                  "extradata" : extradata if extradata else b''}

    try:
        data = serialize_deck_extended_data(net_query(provider.network), params=params)
    except InvalidAddress:
        raise ei.PacliInputDataError("Invalid address.")
    return data

def advanced_deck_spawn(name: str, number_of_decimals: int, issue_mode: int, asset_specific_data: bytes, change_address: str=None, force: bool=False,
                        confirm: bool=True, verify: bool=False, sign: bool=False, send: bool=False, locktime: int=0, debug: bool=False) -> None:
    """Alternative function for deck spawns. Allows p2pk inputs."""

    change_address = Settings.change if change_address is None else change_address
    main_address = ke.get_main_address()
    network = Settings.network
    production = Settings.production
    version = Settings.deck_version

    new_deck = pa.Deck(name, number_of_decimals, issue_mode, network,
                           production, version, asset_specific_data)

    # TODO re-check: in some occasions this produced a change output even if there are exact coins
    # fix attempt: originally 0.02 were as a fix value in select_inputs, now dynamic based on minimum values for each network.
    # perhaps also revise pypeerassets
    # SEEMS to be a pypeerassets issue, the fix didn't help.

    min_tx_value = dmu.sats_to_coins(legacy_mintx(Settings.network), network_name=Settings.network)
    p2th_fee = min_tx_value if min_tx_value else net_query(Settings.network).from_unit
    op_return_fee = p2th_fee if is_legacy_blockchain(Settings.network, "nulldata") else 0
    all_fees = net_query(Settings.network).min_tx_fee + p2th_fee + op_return_fee

    spawn_tx = pa.deck_spawn(provider=provider,
                          inputs=provider.select_inputs(main_address, all_fees),
                          deck=new_deck,
                          change_address=change_address,
                          locktime=locktime
                          )

    return finalize_tx(spawn_tx, confirm=confirm, verify=verify, sign=sign, ignore_checkpoint=force, send=send)



