from typing import Optional, Union
from decimal import Decimal ### ADDED ### 
import operator
import functools
import fire
import random
import pypeerassets as pa
import json
from prettyprinter import cpprint as pprint

from pypeerassets.pautils import (amount_to_exponent,
                                  exponent_to_amount,
                                  parse_card_transfer_metainfo,
                                  parse_deckspawn_metainfo,
                                  read_tx_opreturn ### ADDED ###
                                  )
from pypeerassets.transactions import NulldataScript, TxIn ### ADDED ###
from pypeerassets.__main__ import get_card_transfer
from pypeerassets.at.dt_entities import SignallingTransaction, LockingTransaction, DonationTransaction, VotingTransaction
from pypeerassets.at.transaction_formats import getfmt, PROPOSAL_FORMAT, SIGNALLING_FORMAT, LOCKING_FORMAT, DONATION_FORMAT, VOTING_FORMAT
from pypeerassets.at.dt_misc_utils import get_votestate

from pacli.provider import provider
from pacli.config import Settings
from pacli.keystore import init_keystore, set_new_key, delete_key, get_key, load_key ### MODIFIED ###
from pacli.tui import print_deck_info, print_deck_list
from pacli.tui import print_card_list
from pacli.export import export_to_csv
from pacli.utils import (cointoolkit_verify,
                         signtx,
                         sendtx)
from pacli.coin import Coin
from pacli.config import (write_default_config,
                          conf_file,
                          default_conf,
                          write_settings)
from pacli.dt_utils import (p2th_id_by_type,
                            check_current_period,
                            get_proposal_tx_from_txid,
                            init_dt_deck,
                            get_period,
                            printout_period)

class Config:

    '''dealing with configuration'''

    def default(self) -> None:
        '''revert to default config'''

        write_default_config(conf_file)

    def set(self, key: str, value: Union[str, bool]) -> None:
        '''change settings'''

        if key not in default_conf.keys():
            raise({'error': 'Invalid setting key.'})

        write_settings(key, value)


class Address:

    '''my personal address'''

    def show(self, pubkey: bool=False, privkey: bool=False, wif: bool=False) -> str:
        '''print address, pubkey or privkey'''

        if pubkey:
            return Settings.key.pubkey
        if privkey:
            return Settings.key.privkey
        if wif:
            return Settings.key.wif

        return Settings.key.address

    @classmethod
    def balance(self) -> float:

        pprint(
            {'balance': float(provider.getbalance(Settings.key.address))}
            )

    def derive(self, key: str) -> str:
        '''derive a new address from <key>'''

        pprint(pa.Kutil(Settings.network, from_string=key).address)

    def random(self, n: int=1) -> list:
        '''generate <n> of random addresses, useful when testing'''

        rand_addr = [pa.Kutil(network=Settings.network).address for i in range(n)]

        pprint(rand_addr)

    def get_unspent(self, amount: int) -> Optional[dict]:
        '''quick find UTXO for this address'''

        try:
            pprint(
                {'UTXOs': provider.select_inputs(Settings.key.address, 0.02)['utxos'][0].__dict__['txid']}
                )
        except KeyError:
            pprint({'error': 'No UTXOs ;('})

    def new_privkey(self, key: str=None, backup: str=None, keyid: str=None, wif: bool=False, force: bool=False) -> str: ### NEW FEATURE ###
        '''import new private key, taking hex or wif format, or generate new key.
           You can assign a key name, otherwise it will become the main key.'''

        if wif:
            new_key = pa.Kutil(network=Settings.network, from_wif=key)
            key = new_key.privkey
        elif (not keyid) and key:
            new_key = pa.Kutil(network=Settings.network, privkey=bytearray.fromhex(key))

        set_new_key(new_key=key, backup_id=backup, key_id=keyid, force=force)

        if not keyid:
            if not new_key:
                new_key = pa.Kutil(network=Settings.network, privkey=bytearray.fromhex(load_key()))
            Settings.key = new_key

        return Settings.key.address # this still doesn't work properly

    def set_main(self, keyid: str, backup: str=None, force: bool=False) -> str: ### NEW FEATURE ###
        '''restores old key from backup and sets as personal address'''

        set_new_key(old_key_backup=keyid, backup_id=backup, force=force)
        Settings.key = pa.Kutil(network=Settings.network, privkey=bytearray.fromhex(load_key()))

        return Settings.key.address

    def show_stored(self, keyid: str, pubkey: bool=False, privkey: bool=False, wif: bool=False) -> str: ### NEW FEATURE ###
        '''shows stored alternative keys'''

        try:
            raw_key = bytearray.fromhex(get_key(keyid))
        except TypeError:
            exc_text = "No key data for key {}".format(keyid)
            raise Exception(exc_text)

        key = pa.Kutil(network=Settings.network, privkey=raw_key)

        if privkey:
             return key.privkey
        elif pubkey:
             return key.pubkey
        elif wif:
             return key.wif
        else:
             return key.address

    def delete_key_from_keyring(self, keyid: str) -> None: ### NEW FEATURE ###
        '''deletes a key with an id. Cannot be used to delete main key.'''
        delete_key(keyid)

    def import_to_wallet(self, accountname: str, keyid: str=None) -> None: ### NEW FEATURE ###
        '''imports main key or any stored key to wallet managed by RPC node.
           TODO: should accountname be mandatory or not?'''
        if keyid:
            pkey = pa.Kutil(network=Settings.network, privkey=bytearray.fromhex(get_key(keyid)))
            wif = pkey.wif
        else:
            wif = Settings.wif
        provider.importprivkey(wif, account_name=accountname)
        

class Deck:

    @classmethod
    def list(self):
        '''find all valid decks and list them.'''

        decks = pa.find_all_valid_decks(provider, Settings.deck_version,
                                        Settings.production)

        print_deck_list(decks)

    @classmethod
    def find(self, key):
        '''
        Find specific deck by key, with key being:
        <id>, <name>, <issuer>, <issue_mode>, <number_of_decimals>
        '''

        decks = pa.find_all_valid_decks(provider,
                                        Settings.deck_version,
                                        Settings.production)
        print_deck_list(
            (d for d in decks if key in d.id or (key in d.to_json().values()))
            )

    @classmethod
    def info(self, deck_id):
        '''display deck info'''

        deck = pa.find_deck(provider, deck_id, Settings.deck_version,
                            Settings.production)
        print_deck_info(deck)

    @classmethod
    def p2th(self, deck_id: str) -> None:
        '''print out deck p2th'''

        pprint(pa.Kutil(network=Settings.network,
                        privkey=bytearray.fromhex(deck_id)).address)

    @classmethod
    def __new(self, name: str, number_of_decimals: int, issue_mode: int,
              asset_specific_data: str=None, locktime=None):
        '''create a new deck.'''

        network = Settings.network
        production = Settings.production
        version = Settings.deck_version

        new_deck = pa.Deck(name, number_of_decimals, issue_mode, network,
                           production, version, asset_specific_data)

        return new_deck

    @classmethod
    def spawn(self, verify: bool=False, sign: bool=False,
              send: bool=False, locktime: int=0, **kwargs) -> None:
        '''prepare deck spawn transaction'''

        deck = self.__new(**kwargs)

        spawn = pa.deck_spawn(provider=provider,
                              inputs=provider.select_inputs(Settings.key.address, 0.02),
                              deck=deck,
                              change_address=Settings.change,
                              locktime=locktime
                              )

        if verify:
            print(
                cointoolkit_verify(spawn.hexlify())
                 )  # link to cointoolkit - verify

        if sign:

            tx = signtx(spawn)

            if send:
                pprint({'txid': sendtx(tx)})

            return {'hex': tx.hexlify()}

        return spawn.hexlify()

    @classmethod
    def encode(self, json: bool=False, **kwargs) -> None:
        '''compose a new deck and print out the protobuf which
           is to be manually inserted in the OP_RETURN of the transaction.'''

        if json:
            pprint(self.__new(**kwargs).metainfo_to_dict)

        pprint({'hex': self.__new(**kwargs).metainfo_to_protobuf.hex()})

    @classmethod
    def decode(self, hex: str) -> None:
        '''decode deck protobuf'''

        script = NulldataScript.unhexlify(hex).decompile().split(' ')[1]

        pprint(parse_deckspawn_metainfo(bytes.fromhex(script),
                                        Settings.deck_version))

    def issue_modes(self):

        im = tuple({mode.name: mode.value} for mode_name, mode in pa.protocol.IssueMode.__members__.items())

        pprint(im)

    def my(self):
        '''list decks spawned from address I control'''

        self.find(Settings.key.address)

    def issue_mode_combo(self, *args: list) -> None:

        pprint(
            {'combo': functools.reduce(operator.or_, *args)
             })

    @classmethod
    def at_spawn_old(self, name, tracked_address, verify: bool=False, sign: bool=False,
              send: bool=False, locktime: int=0, multiplier=1, number_of_decimals=2, version=1) -> None: ### ADDRESSTRACK ###
        '''Wrapper to facilitate addresstrack spawns without having to deal with asset_specific_data.'''
        # TODO: format has changed
        if version == 0:
            asset_specific_data = b"trk:" + tracked_address.encode("utf-8") + b":" + str(multiplier).encode("utf-8")
        elif version == 1:
            b_identifier = b'AT'
            b_multiplier = multiplier.to_bytes(2, "big")
            b_address = tracked_address.encode("utf-8")
            asset_specific_data = b_identifier + b_multiplier + b_address

        return self.spawn(name=name, number_of_decimals=number_of_decimals, issue_mode=0x01, locktime=locktime,
                          asset_specific_data=asset_specific_data, verify=verify, sign=sign, send=send)


    @classmethod
    def dt_spawn(self, name: str, dp_length: int, dp_quantity: int, min_vote: int=0, sdp_periods: int=None, sdp_deck: str=None, verify: bool=False, sign: bool=False, send: bool=False, locktime: int=0, number_of_decimals=2) -> None: ### ADDRESSTRACK ###
        '''Wrapper to facilitate addresstrack DT spawns without having to deal with asset_specific_data.'''

        b_identifier = b'DT' #

        try:

            b_dp_length = dp_length.to_bytes(3, "big")
            b_dp_quantity = dp_quantity.to_bytes(2, "big")
            b_min_vote = min_vote.to_bytes(1, "big")

            if sdp_periods:
                b_sdp_periods = sdp_periods.to_bytes(1, "big")
                #b_sdp_deck = sdp_deck.to_bytes(32, "big")
                b_sdp_deck = bytearray.fromhex(sdp_deck)
                print(b_sdp_deck)
            else:
                b_sdp_periods, b_sdp_deck = b'', b''

        except OverflowError:
            raise ValueError("Deck spawn: at least one parameter overflowed.")

        asset_specific_data = b_identifier + b_dp_length + b_dp_quantity + b_min_vote + b_sdp_periods + b_sdp_deck

        print("asset specific data:", asset_specific_data)

        return self.spawn(name=name, number_of_decimals=number_of_decimals, issue_mode=0x01, locktime=locktime,
                          asset_specific_data=asset_specific_data, verify=verify, sign=sign, send=send)

    def dt_init(self, deckid: str):
        '''Intializes deck and imports all P2TH addresses into node.'''

        init_dt_deck(provider, Settings.network, deckid)


class Card:

    '''card information and manipulation'''

    @classmethod
    def __find_deck(self, deckid) -> Deck:

        deck = pa.find_deck(provider, deckid,
                            Settings.deck_version,
                            Settings.production)

        if deck:
            return deck

    @classmethod
    def __list(self, deckid: str):

        deck = self.__find_deck(deckid)

        try:
            cards = pa.find_all_valid_cards(provider, deck)
        except pa.exceptions.EmptyP2THDirectory as err:
            return err

        return {'cards': list(cards),
                'deck': deck}

    @classmethod
    def list(self, deckid: str):
        '''list the valid cards on this deck'''

        cards = self.__list(deckid)['cards']

        print_card_list(cards)

    def balances(self, deckid: str):
        '''list card balances on this deck'''

        cards, deck = self.__list(deckid).values()

        state = pa.protocol.DeckState(cards)

        balances = [exponent_to_amount(i, deck.number_of_decimals)
                    for i in state.balances.values()]

        pprint(dict(zip(state.balances.keys(), balances)))

    def checksum(self, deckid: str) -> bool:
        '''show deck card checksum'''

        cards, deck = self.__list(deckid).values()

        state = pa.protocol.DeckState(cards)

        pprint({'checksum': state.checksum})

    @staticmethod
    def to_exponent(number_of_decimals, amount):
        '''convert float to exponent'''

        return amount_to_exponent(amount, number_of_decimals)

    @classmethod
    def __new(self, deckid: str, receiver: list=None,
              amount: list=None, asset_specific_data: str=None) -> pa.CardTransfer:
        '''fabricate a new card transaction
        * deck_id - deck in question
        * receiver - list of receivers
        * amount - list of amounts to be sent, must be float
        '''

        deck = self.__find_deck(deckid)

        if isinstance(deck, pa.Deck):
            card = pa.CardTransfer(deck=deck,
                                   receiver=receiver,
                                   amount=[self.to_exponent(deck.number_of_decimals, i)
                                           for i in amount],
                                   version=deck.version,
                                   asset_specific_data=asset_specific_data
                                   )

            return card

        raise Exception({"error": "Deck {deckid} not found.".format(deckid=deckid)})

    @classmethod
    def transfer(self, deckid: str, receiver: list=None, amount: list=None,
                 asset_specific_data: str=None,
                 locktime: int=0, verify: bool=False,
                 sign: bool=False, send: bool=False) -> Optional[dict]:
        '''prepare CardTransfer transaction'''

        print(deckid, receiver, amount)

        card = self.__new(deckid, receiver, amount, asset_specific_data)

        issue = pa.card_transfer(provider=provider,
                                 inputs=provider.select_inputs(Settings.key.address, 0.02),
                                 card=card,
                                 change_address=Settings.change,
                                 locktime=locktime
                                 )

        if verify:
            return cointoolkit_verify(issue.hexlify())  # link to cointoolkit - verify

        if sign:

            tx = signtx(issue)

            if send:
                pprint({'txid': sendtx(tx)})

            pprint({'hex': tx.hexlify()})

        return issue.hexlify()

    @classmethod
    def burn(self, deckid: str, receiver: list=None, amount: list=None,
             asset_specific_data: str=None,
             locktime: int=0, verify: bool=False, sign: bool=False) -> str:
        '''wrapper around self.transfer'''

        return self.transfer(deckid, receiver, amount, asset_specific_data,
                             locktime, verify, sign)

    @classmethod
    def issue(self, deckid: str, receiver: list=None, amount: list=None,
              asset_specific_data: str=None,
              locktime: int=0, verify: bool=False,
              sign: bool=False,
              send: bool=False) -> str:
        '''Wrapper around self.transfer'''

        return self.transfer(deckid, receiver, amount, asset_specific_data,
                             locktime, verify, sign, send)

    @classmethod
    def encode(self, deckid: str, receiver: list=None, amount: list=None,
               asset_specific_data: str=None, json: bool=False) -> str:
        '''compose a new card and print out the protobuf which
           is to be manually inserted in the OP_RETURN of the transaction.'''

        card = self.__new(deckid, receiver, amount, asset_specific_data)

        if json:
            pprint(card.metainfo_to_dict)

        pprint({'hex': card.metainfo_to_protobuf.hex()})

    @classmethod
    def decode(self, hex: str) -> dict:
        '''decode card protobuf'''

        script = NulldataScript.unhexlify(hex).decompile().split(' ')[1]

        pprint(parse_card_transfer_metainfo(bytes.fromhex(script),
                                            Settings.deck_version)
               )

    @classmethod
    def simulate_issue(self, deckid: str=None, ncards: int=10,
                       verify: bool=False,
                       sign: str=False, send: bool=False) -> str:
        '''create a batch of simulated CardIssues on this deck'''

        receiver = [pa.Kutil(network=Settings.network).address for i in range(ncards)]
        amount = [random.randint(1, 100) for i in range(ncards)]

        return self.transfer(deckid=deckid, receiver=receiver, amount=amount,
                             verify=verify, sign=sign, send=send)

    def export(self, deckid: str, filename: str):
        '''export cards to csv'''

        cards = self.__list(deckid)['cards']
        export_to_csv(cards=list(cards), filename=filename)

    def parse(self, deckid: str, cardid: str) -> None:
        '''parse card from txid and print data'''

        deck = self.__find_deck(deckid)
        cards = list(get_card_transfer(provider, deck, cardid))

        for i in cards:
            pprint(i.to_json())

    @classmethod
    def __find_deck_data(self, deckid: str) -> tuple: ### NEW FEATURE - AT ###
        '''returns addresstrack-specific data'''

        deck = self.__find_deck(deckid)

        try:
            tracked_address, multiplier = deck.asset_specific_data.split(b":")[1:3]
        except IndexError:
            raise Exception("Deck has not the correct format for address tracking.")

        return tracked_address.decode("utf-8"), int(multiplier)

    @classmethod ### NEW FEATURE - AT ###
    def at_issue(self, deckid: str, txid: str, receiver: list=None, amount: list=None,
              locktime: int=0, verify: bool=False, sign: bool=False, send: bool=False, force: bool=False) -> str:
        '''To simplify self.issue, all data is taken from the transaction.'''

        tracked_address, multiplier = self.__find_deck_data(deckid)
        spending_tx = provider.getrawtransaction(txid, 1)

        for output in spending_tx["vout"]:
            if tracked_address in output["scriptPubKey"]["addresses"]:
                vout = str(output["n"]).encode("utf-8")
                spent_amount = output["value"] * multiplier
                break
        else:
            raise Exception("No vout of this transaction spends to the tracked address")

        if not receiver: # if there is no receiver, spends to himself.
            receiver = [Settings.key.address]

        if not amount:
            amount = [spent_amount]

        if (sum(amount) != spent_amount) and (not force):
            raise Exception("Amount of cards does not correspond to the spent coins. Use --force to override.")

        # TODO: for now, hardcoded asset data; should be a pa function call
        asset_specific_data = b"tx:" + txid.encode("utf-8") + b":" + vout 


        return self.transfer(deckid=deckid, receiver=receiver, amount=amount, asset_specific_data=asset_specific_data,
                             verify=verify, locktime=locktime, sign=sign, send=send)

    @classmethod ### NEW FEATURE - DT ###
    def dt_issue(self, deckid: str, donation_txid: str, amount: list, donation_vout: int=2, move_txid: str=None, receiver: list=None, locktime: int=0, verify: bool=False, sign: bool=False, send: bool=False, force: bool=False) -> str:
        '''To simplify self.issue, all data is taken from the transaction.'''
        # TODO: Multiplier must be replaced by the max epoch amount!

        deck = self.__find_deck(deckid)
        # multiplier = int.from_bytes(deck.asset_specific_data[2:4], "big") # TODO: hardcoded for now! Take into account that the id bytes (now 2) are considered to be changed to 1.
        spending_tx = provider.getrawtransaction(donation_txid, 1)
        # print(multiplier)

        try:
            spent_amount = spending_tx["vout"][donation_vout]["value"]
        except (IndexError, KeyError):
            raise Exception("No vout of this transaction spends to the tracked address")

        # TODO: this must be changed completely. Multiplier is irrelevant, but we would need the slot data to calculate the amount automatically. Maybe make amount mandatory and throw out the whole part until we have an interface for slots.
        # max_amount = spent_amount * multiplier

        if not receiver: # if there is no receiver, spends to himself.
            receiver = [Settings.key.address]

        #if not amount:
        #    amount = [max_amount]

        #elif (sum(amount) != max_amount) and (not force):
        #    raise Exception("Amount of cards does not correspond to the spent coins. Use --force to override.")

        # TODO: for now, hardcoded asset data; should be a ppa function call
        b_id = b'DT'
        b_donation_txid = bytes.fromhex(donation_txid)
        b_vout = int.to_bytes(donation_vout, 1, "big")
        b_move_txid = bytes.fromhex(move_txid) if move_txid else b''
        asset_specific_data = b_id + b_donation_txid + b_vout + b_move_txid

        print("ASD", asset_specific_data)


        return self.transfer(deckid=deckid, receiver=receiver, amount=amount, asset_specific_data=asset_specific_data,
                             verify=verify, locktime=locktime, sign=sign, send=send)



    def at_issue_all(self, deckid: str) -> str:
        '''this function checks all transactions from own address to tracked address and then issues tx.'''

        deck = self.__find_deck(deckid)
        tracked_address = deck.asset_specific_data.split(b":")[1].decode("utf-8")
         # UNFINISHED #


class Transaction:

    def raw(self, txid: str) -> None:
        '''fetch raw tx and display it'''

        tx = provider.getrawtransaction(txid, 1)

        pprint(json.dumps(tx, indent=4))

    def sendraw(self, rawtx: str) -> None:
        '''sendrawtransaction, returns the txid'''

        txid = provider.sendrawtransaction(rawtx)

        pprint({'txid': txid})

    def _select_utxo(self, amount: Decimal=Decimal("0"), tx_fee: Decimal=Decimal("0.01"), p2th_fee: Decimal=Decimal("0.01")):
        ### AT: selects an utxo with suitable amount and lowest possible confirmation number (to not waste coinage)
        ### TODO: This probably should go into into the dt_utils file.
        ### TODO: Should provide an option to select the specific utxo of the previous transaction in the chain (signalling -> locking -> donation).
        utxos = provider.listunspent(address=Settings.key.address)
        selected_utxo = None
        minconf = None

        for utxo in utxos:

            utxo_amount = Decimal(str(utxo["amount"]))
            required_amount = amount + tx_fee + p2th_fee

            if utxo_amount >= required_amount: # amount + minimal tx fee + p2th fee if needed
                 # selects the utxo with less confirmations, so not too much coinage is wasted
                 if (minconf is None) or (utxo["confirmations"] < minconf) and (utxo["confirmations"] > 1):
                     minconf = utxo["confirmations"]
                     selected_utxo = utxo

        if not selected_utxo:
            raise Exception("No utxos with suitable amount found. Please fund address or consolidate UTXOs.")

        return selected_utxo

    def _create_rawtx(self, selected_utxo: dict, dest_address: str=None, p2th_address: str=None, amount: Decimal=Decimal("0"), tx_fee: Decimal=Decimal("0.01"), p2th_fee: Decimal=Decimal("0"), change_address: str=None, op_return_data: bytes=None):
        ### AT: creates inputs and outputs of a donation/signalling/proposal tx
        ### TODO: for now it uses only 1 UTXO.
        ### Can also create txes only with P2TH (without value transfer) like Proposals.
        ### TODO: this has difficulties to create OP_RETURN exactly in the second output.

        if not change_address:
            change_address = Settings.key.address
        if change_address == dest_address:
            raise Exception("Change address is the same than destination. Please provide a different one.")

        MINVAL = Decimal("0.000001") # minimal value in PPC and SLM 

        change_amount = Decimal(str(selected_utxo["amount"])) - amount - tx_fee - p2th_fee
        tx_inputs = [{"txid": selected_utxo["txid"], "vout": selected_utxo["vout"]}]

        tx_outputs = {}

        if p2th_address: # this always is present for TrackedTransactions, but leaving "if" in the case of needing it for other kinds of txs.
            tx_outputs.update({ p2th_address : str(p2th_fee) })

        if op_return_data:
            tx_outputs.update({ "data" : str(op_return_data) })

        # Note: dest_address and change_address cannot be the same one!
        if dest_address and (amount >= MINVAL):
            tx_outputs.update({ dest_address : str(amount) })

        if change_amount >= MINVAL: 
            tx_outputs.update({ change_address : str(change_amount) })

        #print(tx_inputs)
        #print(tx_outputs)

        return provider.createrawtransaction(tx_inputs, tx_outputs)
 

    def at_send_to_tracked_address(self, deckid: str, raw_amount: float, change_address: str=None, sign: bool=False, send: bool=False) -> None: ### ADDRESSTRACK: SEND TO ### ### OLD ADDRESSTRACK ###
        '''this creates a compliant transaction to the donation address.'''
        # TODO: Should be pretty printed at the end like with other pacli transactions.
        ### PRELIMINARY version with hardcoded positions. ###

        amount = str(raw_amount)
        min_fee = Decimal("0.01")
        minconf = None
        selected_utxo = None

        deck = pa.find_deck(provider, deckid,
                            Settings.deck_version,
                            Settings.production)
        tracked_address = deck.asset_specific_data.split(b":")[1].decode("utf-8")
        print("Sending {} coins to tracked address {}".format(amount, tracked_address))

        # select utxos
        utxos = provider.listunspent(address=Settings.key.address)
        possible_inputs = []
        for utxo in utxos: ## This should become a function. TODO ##
            utxo_amount = Decimal(str(utxo["amount"]))
            if utxo_amount >= (Decimal(amount) + min_fee): # amount + minimal tx fee
                 # selects the utxo with less confirmations, so not too much coinage is wasted
                 if (minconf is None) or (utxo["confirmations"] < minconf):
                     minconf = utxo["confirmations"]
                     selected_utxo = utxo

        if not selected_utxo:
            raise Exception("No utxos with suitable amount found. Please fund address or consolidate UTXOs.")

        if not change_address:
            change_address = Settings.key.address

        change_amount = Decimal(str(selected_utxo["amount"])) - Decimal(amount) - min_fee
        tx_inputs = [{"txid": selected_utxo["txid"], "vout": selected_utxo["vout"]}]
        if change_amount < Decimal("0.000001"): # minimal value in PPC and SLM
            tx_outputs = { tracked_address : amount }
        else:
            tx_outputs = { tracked_address : amount, change_address : str(change_amount) }

        rawtx = provider.createrawtransaction(tx_inputs, tx_outputs)
        print(rawtx)

        if sign:
            signedtx = provider.signrawtransaction(rawtx)
            print(signedtx)

        if send:
            self.sendraw(signedtx["hex"])

    def dt_create_proposal(self, deckid: str, req_amount: int, periods: int, p2th_fee: Decimal=Decimal("0.01"), tx_fee: Decimal=Decimal("0.01"), slot_allocation_duration: int=1000, first_ptx: str=None, change_address: str=None, sign: bool=False, send: bool=False):
        ### PRELIMINARY VERSION with hardcoded positions ###
        """PROPOSAL_FORMAT = { "id" : (0, ID_LEN), # identification of proposal txes, 2 bytes
                    "dck" : (ID_LEN, TX_LEN), # deck, 32 bytes
                    "eps" : (ID_LEN + TX_LEN, EPOCH_LEN), # epochs the "worker" needs, 2 bytes
                    "sla" : (ID_LEN + TX_LEN + EPOCH_LEN, SLOTAC_LEN), # slot allocation period, 2 bytes
                    "amt" : (ID_LEN + TX_LEN + EPOCH_LEN + SLOTAC_LEN, AMOUNT_LEN), # amount, 6 bytes
                    "ptx" : (TX_LEN + EPOCH_LEN + SLOTAC_LEN + AMOUNT_LEN, TX_LEN) # previous proposal (optional), 32 bytes
                  }"""
        p2th_id = p2th_id_by_type(deckid, "proposal")
        p2th_address = pa.Kutil(network=Settings.network,
                         privkey=bytearray.fromhex(p2th_id)).address
        b_id = b'DP'
        b_dck = bytes.fromhex(deckid)
        b_prd = periods.to_bytes(2, "big")
        b_sla = slot_allocation_duration.to_bytes(2, "big")
        b_amt = req_amount.to_bytes(6, "big")
        b_ptx = bytes.fromhex(first_ptx) if first_ptx else b'' # workaround for simplicity
        op_return_bytes = b_id + b_dck + b_prd + b_sla + b_amt + b_ptx
        #print(op_return_bytes)

        selected_utxo = self._select_utxo(p2th_fee=p2th_fee, tx_fee=tx_fee)

        rawtx = self._create_rawtx(selected_utxo=selected_utxo, p2th_address=p2th_address, tx_fee=tx_fee, p2th_fee=p2th_fee, change_address=change_address, op_return_data=op_return_bytes.hex())

        print(rawtx)
        if sign:
            signedtx = provider.signrawtransaction(rawtx)
            print(signedtx)

        if send:
            self.sendraw(signedtx["hex"])
        

    def dt_signal_funds(self, deckid: str, proposal_txid: str, raw_amount: str, dest_address: str, change_address: str=None, tx_fee: Decimal=Decimal("0.01"), p2th_fee: Decimal=Decimal("0.01"), sign: bool=False, send: bool=False, check_round: int=None, wait: bool=False) -> None: ### ADDRESSTRACK: SEND TO ###
        '''this creates a compliant signalling transaction.'''

        if check_round is not None:
            if not check_current_period(provider, proposal_txid, "signalling", dist_round=check_round, wait=wait):
                return
        
        str_amount = str(raw_amount)
        amount = Decimal(str_amount)
        minconf = None
        
        p2th_id = p2th_id_by_type(deckid, "signalling")
        p2th_address = pa.Kutil(network=Settings.network,
                         privkey=bytearray.fromhex(p2th_id)).address

        b_id = b'DS'
        b_prp = bytes.fromhex(proposal_txid)
        b_dck = bytes.fromhex(deckid)
        op_return_bytes = b_id + b_prp + b_dck

        print("Signalling {} coins to address {}".format(amount, dest_address))

        # select utxos
        selected_utxo = self._select_utxo(amount=amount, p2th_fee=p2th_fee, tx_fee=tx_fee)

        rawtx = self._create_rawtx(selected_utxo=selected_utxo, dest_address=dest_address, amount=amount, p2th_address=p2th_address, tx_fee=tx_fee, p2th_fee=p2th_fee, change_address=change_address, op_return_data=op_return_bytes.hex())

        print(rawtx)

        if sign:
            signedtx = provider.signrawtransaction(rawtx)
            print(signedtx)

        if send:
            self.sendraw(signedtx["hex"])


    def dt_donate_funds(self, deckid: str, proposal_txid: str, raw_amount: str, change_address: str=None, tx_fee: str="0.01", p2th_fee: str="0.01", sign: bool=False, send: bool=False, check_round: int=None, wait: bool=False) -> None: ### ADDRESSTRACK ###
        '''this creates a compliant donation transaction.'''
        # TODO: Does not check if it was correctly signalled.
        # Ideally it should check to use only a SignallingTransaction's funds.
        # TODO: Still does not handle ReserveAmounts. This must be done via the "change address"

        if check_round is not None:
            if not check_current_period(provider, proposal_txid, "donation", dist_round=check_round, wait=wait):
                return

        str_amount = str(raw_amount)
        amount = Decimal(str_amount)
        print(tx_fee, type(tx_fee))
        tx_fee = Decimal(tx_fee)
        p2th_fee = Decimal(p2th_fee)
        minconf = None
       
        # dest_address: needs proposal data.
        # donates automatically to the Proposal address.
        ptx_json = provider.getrawtransaction(proposal_txid, 1)
        ptxprev_json = provider.getrawtransaction(ptx_json["vin"][0]["txid"], 1)
        # print(ptxprev_json)
        ptxprev_vout = ptx_json["vin"][0]["vout"]
        dest_address = ptxprev_json["vout"][ptxprev_vout]["scriptPubKey"]["addresses"][0]
        # TODO: still not decided if we change the format for the donation address and add an item to OP_RETURN.
        # However we always will have to check if it's correct.
        #p_opreturn_hex = ptx_json["vout"][1]["scriptPubKey"]["asm"][10:] # second output has opreturn
        #p_opreturn_bytes = bytes.fromhex(p_opreturn_hex)
        
        p2th_id = p2th_id_by_type(deckid, "donation")
        p2th_address = pa.Kutil(network=Settings.network,
                         privkey=bytearray.fromhex(p2th_id)).address

        b_id = b'DD'
        b_prp = bytes.fromhex(proposal_txid)
        b_dck = bytes.fromhex(deckid)
        op_return_bytes = b_id + b_prp + b_dck

        print("Donating {} coins to address {}".format(amount, dest_address))

        # select utxos
        selected_utxo = self._select_utxo(amount=amount, p2th_fee=p2th_fee, tx_fee=tx_fee)

        rawtx = self._create_rawtx(selected_utxo=selected_utxo, dest_address=dest_address, amount=amount, p2th_address=p2th_address, tx_fee=tx_fee, p2th_fee=p2th_fee, change_address=change_address, op_return_data=op_return_bytes.hex())

        print(rawtx)

        if sign:
            signedtx = provider.signrawtransaction(rawtx)
            print(signedtx)

        if send:
            self.sendraw(signedtx["hex"])

    def dt_lock_funds(self, deckid: str, proposal_txid: str, raw_amount: str, change_address: str=None, tx_fee: str="0.01", p2th_fee: str="0.01", sign: bool=False, send: bool=False, check_round: int=None, wait: bool=False) -> None: ### ADDRESSTRACK ###
        '''this creates a compliant locking transaction.'''
        # TODO: WIP (LockingTransaction creation still does not work properly)
        # TODO: Does not check if it was correctly signalled.
        # TODO: Still does not handle ReserveAmounts. This has to be done via "change address".
        # Ideally it should check to use only a SignallingTransaction's funds.

        if check_round is not None:
            if not check_current_period(provider, proposal_txid, "donation", dist_round=check_round, wait=wait):
                return

        amount = Decimal(str(raw_amount))
        tx_fee = Decimal(str(tx_fee))
        p2th_fee = Decimal(str(p2th_fee))
        minconf = None        
       
        # dest_address: needs proposal data.
        # donates automatically to the Proposal address.
        # ptx_json = provider.getrawtransaction(proposal_txid, 1)
        #ptxprev_json = provider.getrawtransaction(ptx_json["vin"][0]["txid"], 1)
        # print(ptxprev_json)
        #ptxprev_vout = ptx_json["vin"][0]["vout"]
        #dest_address = ptxprev_json["vout"][ptxprev_vout]["scriptPubKey"]["addresses"][0]
        # TODO: still not decided if we change the format for the donation address and add an item to OP_RETURN.
        # However we always will have to check if it's correct.
        #p_opreturn = read_tx_opreturn(ptx_json["vout"][1])
        #proposal_end = ptx_jsongetfmt(p_opreturn, PROPOSAL_FORMAT, "eps")
        first_proposal_tx = get_proposal_tx_from_txid(provider, proposal_txid)
        # TODO it would be even more elegant if we can set the timelock automatically in a LockingTransaction.__init__
        timelock = first_proposal_tx.end_epoch * first_proposal_tx.deck.epoch_length

        p2th_id = p2th_id_by_type(deckid, "donation")
        p2th_address = pa.Kutil(network=Settings.network,
                         privkey=bytearray.fromhex(p2th_id)).address

        b_id = b'DD'
        b_prp = bytes.fromhex(proposal_txid)
        b_dck = bytes.fromhex(deckid)
        op_return_bytes = b_id + b_prp + b_dck

        print("Donating {} coins to address {}".format(amount, dest_address))

        # select utxos
        selected_utxo = TxIn.from_json(self._select_utxo(amount=amount, p2th_fee=p2th_fee, tx_fee=tx_fee))

        ltx = LockingTransaction(proposal_txid=proposal_txid, timelock=timelock, d_address=d_address, d_amount=amount, reserved_amount=None, reserve_address=None, signalling_tx=None, previous_dtx=None, network="tppc", timestamp=None, provider=provider, datastr=op_return_bytes, p2th_address=p2th_address, p2th_fee=p2th_fee, ins=[selected_utxo])

        # rawtx = self._create_rawtx(selected_utxo=selected_utxo, dest_address=dest_address, amount=amount, p2th_address=p2th_address, tx_fee=tx_fee, p2th_fee=p2th_fee, change_address=change_address, op_return_data=op_return_bytes.hex())

        # what is still needed:
        # - inputs (we can use _select_utxo for now?)
        # locktime 
        # check if outputs are correct.

        rawtx = ltx.serialize()

        print(rawtx)

        if sign:
            signedtx = provider.signrawtransaction(rawtx)
            print(signedtx)

        if send:
            self.sendraw(signedtx["hex"])


    def dt_vote(self, proposal_tx: str, vote: str, deckid: str=None, p2th_fee: Decimal=Decimal("0.01"), tx_fee: Decimal=Decimal("0.01"), change_address: str=None, sign: bool=False, send: bool=False, check_phase: int=None, wait: bool=False):

        # TODO: deckid could be trashed, as we have the proposal_tx parameter.

        if check_phase is not None:
            print("Checking blockheights of phase", check_phase, "...")
            if not check_current_period(provider, proposal_tx, "voting", phase=check_phase, wait=wait):
                return

        if not deckid:
            opreturn_out = provider.getrawtransaction(proposal_tx, 1)["vout"][1]
            opreturn = read_tx_opreturn(opreturn_out)
            deck_bytes = getfmt(opreturn, PROPOSAL_FORMAT, "dck")
            deckid = str(deck_bytes.hex())

        p2th_id = p2th_id_by_type(deckid, "voting")
        p2th_address = pa.Kutil(network=Settings.network,
                         privkey=bytearray.fromhex(p2th_id)).address
        b_id = b'DV'
        b_ptx = bytes.fromhex(proposal_tx)

        if vote in ("+", "positive", "p", "1", "yes", "y", "true"):
            b_vot = b'+'
        elif vote in ("-", "negative", "n", "0", "no", "n", "false"):
            b_vot = b'-'
        else:
            raise ValueError("Incorrect vote. Vote with 'positive'/'yes' or 'negative'/'no'.")

        vote_readable = "Positive" if b_vot == b'+' else "Negative" 
        print("Vote:", vote_readable ,"\nProposal:", proposal_tx,"\nDeck:", deckid)

        op_return_bytes = b_id + b_ptx + b_vot

        selected_utxo = self._select_utxo(p2th_fee=p2th_fee, tx_fee=tx_fee)

        rawtx = self._create_rawtx(selected_utxo=selected_utxo, p2th_address=p2th_address, tx_fee=tx_fee, p2th_fee=p2th_fee, change_address=change_address, op_return_data=op_return_bytes.hex())

        print(rawtx)
        if sign:
            signedtx = provider.signrawtransaction(rawtx)
            print(signedtx)

        if send:
            self.sendraw(signedtx["hex"])

class Proposal: ### DT ###

    def dt_get_votes(self, proposal_txid: str, phase: int=0, debug: bool=False):

        votes = get_votestate(provider, proposal_txid, phase, debug)

        pprint("Positive votes (weighted): " + str(votes["positive"]))
        pprint("Negative votes (weighted): " + str(votes["negative"]))

        approval_state = "approved." if votes["positive"] > votes["negative"] else "not approved."
        pprint("In this round, the proposal was " + approval_state)

    def current_period(self, proposal_txid: str, blockheight: int=None):

        period = get_period(provider, proposal_txid, blockheight)
        pprint(printout_period(period))


def main():

    init_keystore()

    fire.Fire({
        'config': Config(),
        'deck': Deck(),
        'card': Card(),
        'address': Address(),
        'transaction': Transaction(),
        'coin': Coin(),
        'proposal' : Proposal()
        })


if __name__ == '__main__':
    main()
