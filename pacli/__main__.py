from typing import Optional, Union
import operator
import functools
import fire
import random
import pypeerassets as pa
import json
from prettyprinter import cpprint as pprint
from pprint import pprint as alt_pprint

from pypeerassets.pautils import (amount_to_exponent,
                                  exponent_to_amount,
                                  parse_card_transfer_metainfo,
                                  parse_deckspawn_metainfo
                                  )
from pypeerassets.transactions import NulldataScript
from pypeerassets.__main__ import get_card_transfer
from pypeerassets.at.transaction_formats import setfmt

from pacli.provider import provider
from pacli.config import Settings
from pacli.keystore import init_keystore, load_key ### MODIFIED ###
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

import pacli.dt_commands as dc
import pacli.keystore_extended as ke
from pacli.dt_classes import Proposal, Donation
from pacli.dex_classes import Dex

# TODO: P2PK is now supported, but only for the TrackedTransaction class. Extend to deck spawns, card transfers etc.

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

    ### Commands for the Extended Keystore (keystore_extended module)
    ### Allows to use more than one address/key

    def new_privkey(self, label: str, key: str=None, backup: str=None, wif: bool=False, legacy: bool=False) -> str:
        '''import new private key, taking hex or wif format, or generate new key.
           You can assign a label, otherwise it will become the main key.'''

        return ke.new_privkey(label, key=key, backup=backup, wif=wif, legacy=legacy)

    def fresh(self, label: str, show: bool=True, set_main: bool=False, backup: str=None, legacy: bool=False):
        '''This function uses the standard client commands to create an address/key and assigns it a label.'''

        return ke.fresh_address(label, show=show, set_main=set_main, backup=backup, legacy=legacy)

    def set_main(self, label: str, backup: str=None, legacy: bool=False) -> str:
        '''Declares a key identified by a label as the main one.'''

        ke.set_new_key(existing_label=label, backup_id=backup, network_name=Settings.network, legacy=legacy)
        Settings.key = pa.Kutil(network=Settings.network, privkey=bytearray.fromhex(load_key()))

        return Settings.key.address

    def show_stored(self, label: str, pubkey: bool=False, privkey: bool=False, wif: bool=False, legacy: bool=False) -> str:
        '''Shows a stored alternative address or key.'''
        # WARNING: Can expose private keys. Try to use 'privkey' and 'wif' options only on testnet.
        return ke.show_stored_key(label, Settings.network, pubkey=pubkey, privkey=privkey, wif=wif, legacy=legacy)

    def show_all(self, debug: bool=False, legacy: bool=False):
        '''Shows all stored addresses and their balance (Unix only).'''
        return ke.show_all_keys(debug, legacy)

    def show_label(self, address=Settings.key.address):
        '''Shows the label of the current main address, or of another address.'''
        return ke.show_label(address)

    def delete_key_from_keyring(self, label: str, legacy: bool=False) -> None: ### NEW FEATURE ###
        '''deletes a key with an user-defined label. Cannot be used to delete main key.'''
        return ke.delete_key_from_keyring(label, legacy=legacy)

    def import_to_wallet(self, accountname: str, label: str=None, legacy: bool=False) -> None: ### NEW FEATURE ###
        '''imports main key or any stored key to wallet managed by RPC node.'''

        return ke.import_key_to_wallet(accountname, label, legacy)

    def my_votes(self, deckid: str, address: str=Settings.key.address):
        '''shows votes cast from this address, for all proposals of a deck.'''
        return dc.show_votes_by_address(deckid, address)

    def my_donations(self, deckid: str, address: str=Settings.key.address):
        '''shows donation states involving this address, for all proposals of a deck.'''
        return dc.show_donations_by_address(deckid, address)


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
        #TODO: transform into new format without the manual byte setting

        b_identifier = b'DT'

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

        return self.spawn(name=name, number_of_decimals=number_of_decimals, issue_mode=0x01, locktime=locktime,
                          asset_specific_data=asset_specific_data, verify=verify, sign=sign, send=send)

    def init(self, deckid: str):
        '''Initializes deck and imports its P2TH address into node.'''
        dc.init_deck(Settings.network, deckid)

    def dt_init(self, deckid: str):
        '''Initializes DT deck and imports all P2TH addresses into node.'''

        dc.init_dt_deck(Settings.network, deckid)

    def dt_info(self, deckid: str, p2th: bool=False):
        '''Prints DT-specific deck info.'''

        pprint(dc.get_deckinfo(deckid, p2th))

    @classmethod
    def dt_list(self):
        '''List all DT decks.'''

        dt_decklist = dc.list_dt_decks()
        print_deck_list(dt_decklist)

    def dt_state(self, deckid: str, debug: bool=False):
        '''Prints the DT deck state.'''
        dc.dt_state(deckid, debug)


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
    def claim_pod_tokens(self, proposal_id: str, donor_address:str=None, payment: list=None, receiver: list=None, locktime: int=0, donation_vout: int=2, donation_txid: str=None, donation_state: str=None, proposer: bool=False, verify: bool=False, sign: bool=False, send: bool=False, force: bool=False, debug: bool=False) -> str:
        '''Issue Proof-of-donation tokens after a successful donation.'''

        if donor_address is None:
            donor_address = Settings.key.address
        else:
            print("You provided a custom address. You will only be able to do a dry run, not to actually claim tokens.\n--sign and --send are disabled, and if you sign the transaction manually it will be invalid.")
            sign, send = False, False

        try:
            asset_specific_data, receiver, payment, deckid = dc.claim_pod_tokens(proposal_id, donor_address=donor_address, payment=payment, receiver=receiver, donation_vout=donation_vout, donation_txid=donation_txid, donation_state=donation_state, proposer=proposer, force=force, debug=debug)
        except TypeError:
            return None

        return self.transfer(deckid=deckid, receiver=receiver, amount=payment, asset_specific_data=asset_specific_data,
                             verify=verify, locktime=locktime, sign=sign, send=send)

    @classmethod
    def simple_transfer(self, deckid: str, receiver: str, amount: str, sign: bool=False, send: bool=False):
        '''Simplified transfer with only one single payment.'''
        return self.transfer(deckid, receiver=[receiver], amount=[amount], sign=sign, send=send)

    #@classmethod
    #def at_issue_all(self, deckid: str) -> str:
    #    '''this function checks all transactions from own address to tracked address and then issues tx.'''
    #
    #    deck = self.__find_deck(deckid)
    #    tracked_address = deck.asset_specific_data.split(b":")[1].decode("utf-8")
    #     # UNFINISHED #

class Transaction:

    def raw(self, txid: str) -> None:
        '''fetch raw tx and display it'''

        tx = provider.getrawtransaction(txid, 1)

        pprint(json.dumps(tx, indent=4))

    def sendraw(self, rawtx: str) -> None:
        '''sendrawtransaction, returns the txid'''

        txid = provider.sendrawtransaction(rawtx)

        pprint({'txid': txid})


def main():

    init_keystore()

    fire.Fire({
        'config': Config(),
        'deck': Deck(),
        'card': Card(),
        'address': Address(),
        'transaction': Transaction(),
        'coin': Coin(),
        'proposal' : Proposal(),
        'donation' : Donation()
        })


if __name__ == '__main__':
    main()
