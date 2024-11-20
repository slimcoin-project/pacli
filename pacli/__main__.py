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

import pacli.keystore_extended as ke
import pacli.extended_utils as eu
import pacli.extended_commands as ec
from pacli.extended_classes import ExtConfig, ExtAddress, ExtDeck, ExtCard, ExtTransaction
from pacli.at_classes import ATToken, PoBToken
from pacli.at_utils import create_at_issuance_data, at_deckinfo
from pacli.dt_classes import PoDToken, Proposal, Donation
from pacli.dex_classes import Swap
from pacli.extended_checkpoints import Checkpoint

# NOTE: pacli-extended overrides some vanilla methods due to its usage of an extended config file.
# These methods are commented out here and the extended classes are placed in extended_classes.py.
# The idea is to keep the original pacli files clean and pack the extensions in their own files.

class Config(ExtConfig):

    """Commands to manage configuration settings."""

    pass

    """def default(self) -> None:
        '''revert to default config'''

        write_default_config(conf_file)"""

    """def set(self, key: str, value: Union[str, bool]) -> None:
        '''change settings'''

        if key not in default_conf.keys():
            raise({'error': 'Invalid setting key.'})

        write_settings(key, value)""" # disabled due to ExtConfig conflict


class Address(ExtAddress):

    """Commands managing the main personal address and other addresses."""

    """def show(self, pubkey: bool=False, privkey: bool=False, wif: bool=False) -> str:
        '''print address, pubkey or privkey'''

        if pubkey:
            return Settings.key.pubkey
        if privkey:
            return Settings.key.privkey
        if wif:
            return Settings.key.wif

        return Settings.key.address""" # disabled due to ExtAddress conflict.

    """@classmethod
    def balance(self) -> float:

        pprint(
            {'balance': float(provider.getbalance(Settings.key.address))}
            )""" # disabled due to ExtAddress conflict.

    def derive(self, key: str) -> str:
        '''derive a new address from <key>'''

        pprint(pa.Kutil(Settings.network, from_string=key).address)

    def random(self, n: int=1) -> list:
        '''generate <n> of random addresses, useful when testing'''

        rand_addr = [pa.Kutil(network=Settings.network).address for i in range(n)]

        pprint(rand_addr)

    def get_unspent(self) -> Optional[dict]:
        '''Quickly find an UTXO for this address which is able to spend 0.02 fees for a PeerAssets transaction.'''

        try:
            pprint(
                {'UTXOs': provider.select_inputs(Settings.key.address, 0.02)['utxos'][0].__dict__['txid']}
                )
        except KeyError:
            pprint({'error': 'No UTXOs ;('})


class Deck(ExtDeck):

    '''Commands to manage token decks.'''

    """@classmethod
    def list(self):
        '''find all valid decks and list them.'''

        decks = pa.find_all_valid_decks(provider, Settings.deck_version,
                                        Settings.production)

        print_deck_list(decks)""" # disabled due to ExtDeck conflict.

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
            (d for d in decks if str(key) in d.id or (str(key) in d.to_json().values()))
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
    def spawn(self, name: str,
              number_of_decimals: int, issue_mode: int,
              asset_specific_data: str=None,
              verify: bool=False, sign: bool=False,
              send: bool=False, locktime: int=0) -> None:
        '''prepare deck spawn transaction'''
        ## replaced **kwargs with the deck.__new args, this prevented the help to work

        # deck = self.__new(**kwargs)
        deck = self.__new(name, number_of_decimals, issue_mode,
                          asset_specific_data=asset_specific_data, locktime=locktime)

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
    def encode(self,  name: str,
              number_of_decimals: int, issue_mode: int,
              asset_specific_data: str=None, json: bool=False,
              locktime: int=0) -> None:
        '''compose a new deck and print out the protobuf which
           is to be manually inserted in the OP_RETURN of the transaction.'''
        # replaced deck __new arguments, see deck spawn.

        deck = self.__new(name, number_of_decimals, issue_mode,
                          asset_specific_data=asset_specific_data, locktime=locktime)

        if json:
            # pprint(self.__new(**kwargs).metainfo_to_dict)
            pprint(deck.metainfo_to_dict)

        # pprint({'hex': self.__new(**kwargs).metainfo_to_protobuf.hex()})
        pprint({'hex': deck.metainfo_to_protobuf.hex()})

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


class Card(ExtCard):

    """Commands for card information and manipulation."""

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

    """@classmethod
    def list(self, deckid: str):
        '''list the valid cards on this deck'''

        cards = self.__list(deckid)['cards']

        print_card_list(cards)""" # disabled due to ExtCard conflict

    """def balances(self, deckid: str):
        '''list card balances on this deck'''

        cards, deck = self.__list(deckid).values()

        state = pa.protocol.DeckState(cards)

        balances = [exponent_to_amount(i, deck.number_of_decimals)
                    for i in state.balances.values()]

        pprint(dict(zip(state.balances.keys(), balances)))""" # disabled, replaced by ExtCard

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

    """@classmethod
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

        return issue.hexlify()""" # replaced by ExtCard method

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
        """Encodes a token transaction (card) into protobuf format.

        Usage:

            pacli card encode TOKENID [RECEIVERS] [AMOUNTS]
            pacli token encode_transfer TOKENID [RECEIVERS] [AMOUNTS]

        Compose a new card and print out the protobuf which
        is to be manually inserted in the OP_RETURN of the transaction.

        Args:

            receiver: List of receivers.
            amount: List of amounts, in the same order and number as the receivers.
            asset_specific_data: Arbitrary data attached to the card.
            json: Use JSON output."""


        card = self.__new(deckid, receiver, amount, asset_specific_data)

        if json:
            pprint(card.metainfo_to_dict)

        pprint({'hex': card.metainfo_to_protobuf.hex()})

    @classmethod
    def decode(self, encoded: str) -> dict:
        """Decodes a token transfer (card) protobuf string.

        Usage:

            pacli card decode HEX
            pacli token decode_transfer HEX

        HEX is the encoded transaction/card in protobuf format (see 'card decode'/'token decode')"""
        ### MODIFIED, parameter was first called "hex", which conflicts with "help"

        script = NulldataScript.unhexlify(encoded).decompile().split(' ')[1]

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
        """Parses a token transfer (card) from txid and print data.

        Usage:

             pacli card parse DECKID CARDID
             pacli token parse_transfer DECKID CARDID

        CARDID is the transaction ID of the card.
        """

        deck = self.__find_deck(deckid)
        cards = list(get_card_transfer(provider, deck, cardid))

        for i in cards:
            pprint(i.to_json())

class Transaction(ExtTransaction):

    """Commands for transaction information and creation."""

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

    from pacli.token_class import Token

    fire.Fire({
        'config': Config(),
        'deck': Deck(),
        'card': Card(),
        'address': Address(),
        'transaction': Transaction(),
        'coin': Coin(),
        'proposal' : Proposal(),
        'donation' : Donation(),
        'token' : Token(),
        'attoken' : ATToken(),
        'pobtoken' : PoBToken(),
        'podtoken' : PoDToken(),
        'swap' : Swap(),
        'checkpoint' : Checkpoint()
        })


if __name__ == '__main__':
    main()
