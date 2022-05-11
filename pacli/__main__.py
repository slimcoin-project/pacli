## TODO: this is already the refactored version with Proposal and Donation in an own file!
# removed imports: TxIn, read_tx_opreturn (are probably only used in dt_utils), all dt_entities (only TrackedTransaction was used in the Proposal/Donation class), all transaction formats, getfmt, get_votestate, create_unsigned_tx, get_donation_states, get_proposal_state, coin_value
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
from pacli.keystore import init_keystore, set_new_key, set_key, delete_key, get_key, load_key, get_key_prefix ### MODIFIED ###
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
import pacli.dt_utils as du
import pacli.dt_interface as di
from pacli.dt_classes import Proposal, Donation

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

    def new_privkey(self, label: str, key: str=None, backup: str=None, wif: bool=False, legacy: bool=False) -> str: ### NEW FEATURE ###
        '''import new private key, taking hex or wif format, or generate new key.
           You can assign a label, otherwise it will become the main key.'''

        if wif:
            new_key = pa.Kutil(network=Settings.network, from_wif=key)
            key = new_key.privkey
        elif (not label) and key:
            new_key = pa.Kutil(network=Settings.network, privkey=bytearray.fromhex(key))

        set_new_key(new_key=key, backup_id=backup, label=label, network_name=Settings.network, legacy=legacy)
        fulllabel = get_key_prefix(Settings.network, legacy) + label
        key = get_key(fulllabel)

        if not label:
            if not new_key:
                new_key = pa.Kutil(network=Settings.network, privkey=bytearray.fromhex(load_key()))
            Settings.key = new_key

        return "Address: " + pa.Kutil(network=Settings.network, privkey=bytearray.fromhex(key)).address

    def fresh(self, label: str, show: bool=False, set_main: bool=False, backup: str=None, legacy: bool=False): ### NEW ###
        '''This function uses the standard client commands to create an address/key and assigns it a label.'''
        # NOTE: This command does not assign the address an account name or label in the wallet!
        addr = provider.getnewaddress()
        privkey_wif = provider.dumpprivkey(addr)
        privk_kutil = pa.Kutil(network=Settings.network, from_wif=privkey_wif)
        privkey = privk_kutil.privkey

        fulllabel = get_key_prefix(Settings.network, legacy) + label

        try:
            if fulllabel in du.get_all_labels(Settings.network):
                return "ERROR: Label already used. Please choose another one."
        except ImportError:
            print("NOTE: If you do not use SecretStorage, which is likely if you use Windows, you currently have to make sure yourself you don't use the same label for two or more addresses.")

        set_key(fulllabel, privkey)

        if show:
            print("New address created:", privk_kutil.address, "with label (name):", label)
            print("Address already is saved in your wallet and in your keyring, ready to use.")
        if set_main:
            set_new_key(new_key=privkey, backup_id=backup, label=label, network_name=Settings.network, legacy=legacy)
            Settings.key = privk_kutil
            return Settings.key.address

    def set_main(self, label: str, backup: str=None, legacy: bool=False) -> str: ### NEW FEATURE ###
        '''Declares a key identified by a label as the main one.'''

        set_new_key(existing_label=label, backup_id=backup, network_name=Settings.network, legacy=legacy)
        Settings.key = pa.Kutil(network=Settings.network, privkey=bytearray.fromhex(load_key()))

        return Settings.key.address

    def show_stored(self, label: str, pubkey: bool=False, privkey: bool=False, wif: bool=False, legacy: bool=False) -> str: ### NEW FEATURE ###
        '''shows stored alternative keys'''
        # WARNING: Can expose private keys. Try to use 'privkey' and 'wif' options only on testnet.
        return du.show_stored_key(label, Settings.network, pubkey=pubkey, privkey=privkey, wif=wif, legacy=legacy)

    def show_all(self, debug: bool=False, legacy: bool=False):

        net_prefix = "bak" if legacy else Settings.network

        labels = du.get_all_labels(net_prefix)

        prefix = "key_" + net_prefix + "_"
        print("Address".ljust(35), "Balance".ljust(15), "Label".ljust(15))
        print("---------------------------------------------------------")
        for raw_label in labels:
            try:
                label = raw_label.replace(prefix, "")
                raw_key = bytearray.fromhex(get_key(raw_label))
                key = pa.Kutil(network=Settings.network, privkey=raw_key)
                addr = key.address
                balance = str(provider.getbalance(addr))
                print(addr.ljust(35), balance.ljust(15), label.ljust(15))

            except Exception as e:
                if debug: print("ERROR:", label, e)
                continue

    def show_label(self, address=Settings.key.address):
        '''Shows the label of the current main address, or of another address.'''
        return du.show_label(address)

    def delete_key_from_keyring(self, label: str, legacy: bool=False) -> None: ### NEW FEATURE ###
        '''deletes a key with an id. Cannot be used to delete main key.'''
        prefix = get_key_prefix(Settings.network, legacy)
        try:
           delete_key(prefix + label)
           print("Key", label, "successfully deleted.")
        except keyring.errors.PasswordDeleteError:
           print("Key", label, "does not exist. Nothing deleted.")

    def import_to_wallet(self, accountname: str, label: str=None, legacy: bool=False) -> None: ### NEW FEATURE ###
        '''imports main key or any stored key to wallet managed by RPC node.'''

        prefix = get_key_prefix(Settings.network, legacy)
        if label:
            pkey = pa.Kutil(network=Settings.network, privkey=bytearray.fromhex(get_key(prefix + label)))
            wif = pkey.wif
        else:
            wif = Settings.key.wif
        if Settings.network in ("slm", "tslm"):
            provider.importprivkey(wif, accountname, rescan=True)
        else:
            provider.importprivkey(wif, account_name=accountname)

    def my_votes(self, deckid: str, address: str=Settings.key.address):
        '''shows votes cast from this address, for all proposals of a deck.'''
        return du.show_votes_by_address(deckid, address)

    def my_donations(self, deckid: str, address: str=Settings.key.address):
        '''shows donation states involving this address, for all proposals of a deck.'''
        return du.show_donations_by_address(deckid, address)


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
        du.init_deck(Settings.network, deckid)

    def dt_init(self, deckid: str):
        '''Initializes DT deck and imports all P2TH addresses into node.'''

        du.init_dt_deck(Settings.network, deckid)

    def dt_info(self, deckid: str):
        deckinfo = du.get_deckinfo(deckid)
        pprint(deckinfo)

    @classmethod
    def dt_list(self):
        '''
        List all DT decks.
        '''
        # TODO: This does not catch some errors with invalid decks which are displayed:
        # InvalidDeckSpawn ("InvalidDeck P2TH.") -> not catched in deck_parser in pautils.py
        # 'error': 'OP_RETURN not found.' -> InvalidNulldataOutput , in pautils.py
        # 'error': 'Deck () metainfo incomplete, deck must have a name.' -> also in pautils.py, defined in exceptions.py.

        decks = pa.find_all_valid_decks(provider,
                                        Settings.deck_version,
                                        Settings.production)
        dt_decklist = []
        for d in decks:
            try:
                if d.at_type == "DT":
                    dt_decklist.append(d)
            except AttributeError:
                continue

        print_deck_list(dt_decklist)


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
    def claim_pod_tokens(self, proposal_id: str, donor_address=Settings.key.address, payment: list=None, receiver: list=None, locktime: int=0, deckid: str=None, donation_vout: int=2, donation_txid: str=None, proposer: bool=False, verify: bool=False, sign: bool=False, send: bool=False, force: bool=False, debug: bool=False) -> str:
        '''Issue Proof-of-donation tokens after a successful donation.'''

        if not receiver: # if there is no receiver, the coins are directly allocated to the donor.
            receiver = [Settings.key.address]

        if not force:
            print("Calculating reward ...")
            try:
                reward_data = du.get_pod_reward_data(proposal_id, donor_address, proposer=proposer, debug=debug)
            except Exception as e:
                print(e)
                return None
            deckid = reward_data.get("deckid")
            max_payment = reward_data.get("reward")
            donation_txid = reward_data.get("donation_txid")
        elif not deckid:
            print("ERROR: No deckid provided, if you use --force you need to provide it.")
            return None
        elif payment is not None:
            max_payment = sum(payment)
            print("WARNING: Overriding reward calculation. If you calculated your payment incorrectly, the transaction will be invalid.")
        else:
            print("ERROR: No payment data provided.")
            return None

        if payment is None:
            payment = [max_payment]
        else:
            if sum(payment) > max_payment:
                raise Exception("Amount of cards does not correspond to the spent coins. Use --force to override.")
            rest_amount = max_payment - sum(payment)
            if rest_amount > 0:
                receiver.append(donor_address)
                payment.append(rest_amount)


        params = { "id" : "DT", "dtx" : donation_txid, "out" : donation_vout}
        asset_specific_data = setfmt(params, tx_type="cardissue_dt")

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
