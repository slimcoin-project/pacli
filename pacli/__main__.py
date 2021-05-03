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
from pypeerassets.at.dt_entities import SignallingTransaction, LockingTransaction, DonationTransaction, VotingTransaction, TrackedTransaction, ProposalTransaction
from pypeerassets.at.transaction_formats import getfmt, setfmt, PROPOSAL_FORMAT, SIGNALLING_FORMAT, LOCKING_FORMAT, DONATION_FORMAT, VOTING_FORMAT
from pypeerassets.at.dt_misc_utils import get_votestate, create_unsigned_tx, get_proposal_state

from pacli.provider import provider
from pacli.config import Settings
from pacli.keystore import init_keystore, set_new_key, set_key, delete_key, get_key, load_key ### MODIFIED ###
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

    def new_privkey(self, key: str=None, backup: str=None, label: str=None, wif: bool=False, force: bool=False) -> str: ### NEW FEATURE ###
        '''import new private key, taking hex or wif format, or generate new key.
           You can assign a key name, otherwise it will become the main key.'''

        if wif:
            new_key = pa.Kutil(network=Settings.network, from_wif=key)
            key = new_key.privkey
        elif (not label) and key:
            new_key = pa.Kutil(network=Settings.network, privkey=bytearray.fromhex(key))

        set_new_key(new_key=key, backup_id=backup, label=label, force=force)

        if not label:
            if not new_key:
                new_key = pa.Kutil(network=Settings.network, privkey=bytearray.fromhex(load_key()))
            Settings.key = new_key

        return Settings.key.address # this still doesn't work properly

    def fresh(self, label: str, show: bool=False, set_main: bool=False, force: bool=False, backup: str=None): ### NEW ###
        '''This function uses the standard client commands to create an address/key and assign it a key id.'''
        addr = provider.getnewaddress()
        privkey_wif = provider.dumpprivkey(addr)
        privk_kutil = pa.Kutil(network=Settings.network, from_wif=privkey_wif)
        privkey = privk_kutil.privkey
        fulllabel = "key_bak_" + label
        if fulllabel in du.get_all_labels():
            return "ERROR: Label already used. Please choose another one."

        set_key(fulllabel, privkey)

        if show:
            print("New address created:", privk_kutil.address, "with label (name):", label)
            print("Address already is saved in your wallet and in your keyring, ready to use.")
        if set_main:
            set_new_key(new_key=privkey, backup_id=backup, label=label, force=force)
            Settings.key = privk_kutil
            return Settings.key.address

    def set_main(self, label: str, backup: str=None) -> str: ### NEW FEATURE ###
        '''Declares a key identified by a label as the main one.'''

        set_new_key(existing_label=label, backup_id=backup)
        Settings.key = pa.Kutil(network=Settings.network, privkey=bytearray.fromhex(load_key()))

        return Settings.key.address

    def show_stored(self, label: str, pubkey: bool=False, privkey: bool=False, wif: bool=False) -> str: ### NEW FEATURE ###
        '''shows stored alternative keys'''
        # WARNING: Can expose private keys. Try to use it only on testnet.
        return du.show_stored_key(label, Settings.network, pubkey=pubkey, privkey=privkey, wif=wif)

    def show_all(self, debug: bool=False):
        labels = du.get_all_labels()
        print("Address".ljust(35), "Balance".ljust(15), "Label".ljust(15))
        print("---------------------------------------------------------")
        for raw_label in labels:
            try:
                label = raw_label.replace("key_bak_", "")
                raw_key = bytearray.fromhex(get_key(label))
                key = pa.Kutil(network=Settings.network, privkey=raw_key)
                addr = key.address
                balance = str(provider.getbalance(addr))
                print(addr.ljust(35), balance.ljust(15), label.ljust(15))
                
                      
            except Exception as e:
                if debug: print("ERROR:", label, e)
                continue

    def delete_key_from_keyring(self, label: str) -> None: ### NEW FEATURE ###
        '''deletes a key with an id. Cannot be used to delete main key.'''
        delete_key(label)

    def import_to_wallet(self, accountname: str, label: str=None) -> None: ### NEW FEATURE ###
        '''imports main key or any stored key to wallet managed by RPC node.
           TODO: should accountname be mandatory or not?'''
        if label:
            pkey = pa.Kutil(network=Settings.network, privkey=bytearray.fromhex(get_key(label)))
            wif = pkey.wif
        else:
            wif = Settings.wif
        provider.importprivkey(wif, account_name=accountname)

    def my_votes(self, deckid: str, address: str=Settings.key.address):
        '''shows votes cast from this address.'''
        # TODO: optional weight parameter
        return du.show_votes_by_address(provider, deckid, address)

    def my_donations(self, deckid: str, address: str=Settings.key.address):
        '''shows donation states involving this address.'''
        return du.show_donations_by_address(provider, deckid, address)
        

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

        du.init_dt_deck(provider, Settings.network, deckid)

    def dt_info(self, deckid: str):
        deckinfo = du.get_deckinfo(deckid, provider)
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
    def claim_pod_tokens(self, proposal_id: str, donor_address=Settings.key.address, payment: list=None, receiver: list=None, locktime: int=0, deckid: str=None, donation_vout: int=2, donation_txid: str=None, proposer: bool=False, verify: bool=False, sign: bool=False, send: bool=False, force: bool=False, debug: bool=False) -> str:
        '''Simplified variant of dt_issue, deckid not needed.'''

        if not receiver: # if there is no receiver, the coins are directly allocated to the donor.
            receiver = [Settings.key.address]

        if not force:
            print("Calculating reward ...")
            reward_data = du.get_pod_reward_data(provider, proposal_id, donor_address, proposer=proposer, debug=debug)
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
               
class Proposal: ### DT ###

    def get_votes(self, proposal_txid: str, phase: int=0, debug: bool=False):

        votes = get_votestate(provider, proposal_txid, phase, debug)

        pprint("Positive votes (weighted): " + str(votes["positive"]))
        pprint("Negative votes (weighted): " + str(votes["negative"]))

        approval_state = "approved." if votes["positive"] > votes["negative"] else "not approved."
        pprint("In this round, the proposal was " + approval_state)

    def current_period(self, proposal_txid: str, blockheight: int=None, show_blockheights: bool=True):

        period = du.get_period(provider, proposal_txid, blockheight)
        pprint(du.printout_period(period, show_blockheights))

    def list(self, deckid: str, block: int=None, show_completed: bool=False) -> None:
        '''Shows all proposals and the period they are currently in, optionally at a specific blockheight.'''

        # TODO: Abandoned and completed proposals cannot be separated this way, this needs a more complex
        #       method involving the parser. => Advanced mode could be a good idea.
        # TODO: Printout should be reorganized, so two proposals which overlap by coincidence don't share erroneously the same block heights for start and end.
        if not block:
            block = provider.getblockcount()
            pprint("Current block: " + str(block))

        try:
            pstate_periods = du.get_proposal_state_periods(provider, deckid, block)
        except KeyError:
            pprint("Error, unconfirmed proposals in mempool. Wait until they are confirmed.")
            return
        except ValueError as ve:
            if len(ve.args) > 0:
                pprint(ve.args[0])
            pprint("Deck in wrong format, proposals could not be retrieved.")
            return

        excluded_list = []
        #if show_completed:
        #    statelist.append("completed")
        #if show_abandoned:
        #    statelist.append("abandoned")

        if len([p for l in pstate_periods.values() for p in l]) == 0:
            print("No proposals found for deck: " + deckid)
        else:
            print("Proposals in the following periods are available for this deck:")

        for state in pstate_periods:
            if state not in excluded_list and (len(pstate_periods[state]) > 0):
                print("* " + du.printout_period(state, show_blockheights=True))
                print("** ", end='')
                print("\n** ".join(pstate_periods[state]))

    def info(self, proposal_txid):
        info = du.get_proposal_info(provider, proposal_txid)
        pprint(info)

    def state(self, proposal_txid, debug=False, simple=False, phase=1):
        '''Shows a single proposal state.'''
        pstate = get_proposal_state(provider, proposal_txid, phase=phase, debug=debug)
        if simple:
            pprint(pstate.__dict__)
            print("locking txes:", pstate.all_locking_txes, [ t.txid for t in pstate.all_locking_txes ])
            return
        pdict = pstate.__dict__
        pprint("Proposal State " + proposal_txid + ":")
        du.update_2levels(pdict)
        pprint(pdict)

    def my_donation_states(self, proposal_id: str, address: str=Settings.key.address, debug=False):
        '''Shows the donation states involving a certain address (default: current active address).'''
        dstates = du.get_donation_states(provider, proposal_id, address=address, debug=debug)
        for dstate in dstates:
            pprint("Donation state ID: " + dstate.id)
            #pprint(dstate.__dict__)
            ds_dict = dstate.__dict__
            for item in ds_dict:
                try:
                    value = ds_dict[item].txid
                except AttributeError:
                    value = ds_dict[item]
                print(item + ":", value)

    def all_donation_states(self, proposal_id: str, debug=False):
        dstates = du.get_donation_states(provider, proposal_id, debug=debug)
        for dstate in dstates:
            pprint("Donation state ID: " + dstate.id)

            ds_dict = dstate.__dict__

            for item in ds_dict:

                if issubclass(type(ds_dict[item]), TrackedTransaction):
                    value = ds_dict[item].txid
                else:
                    value = ds_dict[item]

                print(item + ":", value)

    def create(self, deckid: str, req_amount: str, periods: int, slot_allocation_duration: int, change_address: str=None, tx_fee: str="0.01", p2th_fee: str="0.01", input_txid: str=None, input_vout: int=None, input_address: str=Settings.key.address, first_ptx: str=None, sign: bool=False, send: bool=False, verify: bool=False):

        params = { "id" : "DP" , "dck" : deckid, "eps" : int(periods), "sla" : int(slot_allocation_duration), "amt" : int(req_amount), "ptx" : first_ptx}

        rawtx = du.create_unsigned_trackedtx(provider, "proposal", params, deckid=deckid, change_address=change_address, input_address=input_address, raw_tx_fee=tx_fee, raw_p2th_fee=p2th_fee)

        return du.finalize_tx(rawtx, verify, sign, send)

    def vote(self, proposal_id: str, vote: str, p2th_fee: str="0.01", tx_fee: str="0.01", change_address: str=None, input_address: str=Settings.key.address, verify: bool=False, sign: bool=False, send: bool=False, check_phase: int=None, wait: bool=False, confirm: bool=True):

        if (check_phase is not None) or (wait == True):
            print("Checking blockheights ...")
            if not du.check_current_period(provider, proposal_id, "voting", phase=check_phase, wait=wait):
                return

        if vote in ("+", "positive", "p", "1", "yes", "y", "true"):
            votechar = "+"
        elif vote in ("-", "negative", "n", "0", "no", "n", "false"):
            votechar = "-"
        else:
            raise ValueError("Incorrect vote. Vote with 'positive'/'yes' or 'negative'/'no'.")

        vote_readable = "Positive" if votechar == "+" else "Negative" 
        # print("Vote:", vote_readable ,"\nProposal ID:", proposal_id)

        params = { "id" : "DV" , "prp" : proposal_id, "vot" : votechar }

        basic_tx_data = du.get_basic_tx_data(provider, "voting", proposal_id, input_address=input_address)
        rawtx = du.create_unsigned_trackedtx(params, basic_tx_data, change_address=change_address, raw_tx_fee=tx_fee, raw_p2th_fee=p2th_fee)

        console_output = du.finalize_tx(rawtx, verify, sign, send)

        if confirm and sign and send:
            print("Waiting for confirmation (this can take several minutes) ...", end='')
            confirmations = 0
            while confirmations == 0:
                tx = provider.getrawtransaction(rawtx.txid, 1)
                try:
                    confirmations = tx["confirmations"]
                    break
                except KeyError:
                    du.spinner(10)

            print("\nVote confirmed.")

        return console_output

class Donation:

    def signal(self, proposal_txid: str, amount: str, dest_label: str=None, dest_address: str=None, change_address: str=None, tx_fee: str="0.01", p2th_fee: str="0.01", change_label: str=None, sign: bool=False, send: bool=False, verify: bool=False, check_round: int=None, wait: bool=False, input_address: str=Settings.key.address, debug: bool=False) -> None:
        '''this creates a compliant signalling transaction.'''

        [dest_address, change_address] = du.show_addresses([dest_address, change_address], [dest_label, change_label], Settings.network)

        if (check_round is not None) or (wait == True):
            if not du.check_current_period(provider, proposal_txid, "signalling", dist_round=check_round, wait=wait):
                return

            print("You are signalling {} coins.".format(amount))
            print("Take into account that releasing the donation requires 0.02 coins for fees.")
            if (check_round is not None) and (check_round < 4):
                print("Additionally, locking the transaction requires 0.02 coins, so total fees sum up to 0.04.")

        params = { "id" : "DS" , "prp" : proposal_txid }
        basic_tx_data = du.get_basic_tx_data(provider, "signalling", proposal_txid, input_address=Settings.key.address)

        rawtx = du.create_unsigned_trackedtx(params, basic_tx_data, change_address=change_address, dest_address=dest_address, raw_tx_fee=tx_fee, raw_p2th_fee=p2th_fee, raw_amount=amount, debug=debug)

        return du.finalize_tx(rawtx, verify, sign, send)

    def lock(self, proposal_txid: str, amount: str=None, change_address: str=None, dest_address: str=Settings.key.address, tx_fee: str="0.01", p2th_fee: str="0.01", sign: bool=False, send: bool=False, verify: bool=False, check_round: int=None, wait: bool=False, new_inputs: bool=False, dist_round: int=None, manual_timelock: int=None, reserve: str=None, reserve_address: str=None, dest_label: str=None, reserve_label: str=None, change_label: str=None, debug: bool=False) -> None:

        """Locking Transaction locks funds to the origin address (default)."""
        # TODO: dest_address could be trashed completely as the convention is now to use always the donor address.
        [dest_address, reserve_address, change_address] = du.show_addresses([dest_address, reserve_address, change_address], [dest_label, reserve_label, change_label], Settings.network)

        if (check_round is not None) or (wait == True):
            dist_round=check_round
            if not du.check_current_period(provider, proposal_txid, "locking", dist_round=check_round, wait=wait):
                return

        cltv_timelock = int(manual_timelock) if manual_timelock else du.calculate_timelock(provider, proposal_txid)
        print("Locking funds until block", cltv_timelock)

        if amount:
            print("Not using slot, instead locking custom amount:", amount)
            use_slot = False
        else:
            use_slot = True

        # MODIFIED: added timelock and dest_address to be able to reconstruct redeem script
        params = { "id" : "DL", "prp" : proposal_txid, "lck" : cltv_timelock, "adr" : dest_address }
        basic_tx_data = du.get_basic_tx_data(provider, "locking", proposal_txid, input_address=Settings.key.address, new_inputs=new_inputs, use_slot=use_slot)

        rawtx = du.create_unsigned_trackedtx(params, basic_tx_data, dest_address=dest_address, change_address=change_address, raw_tx_fee=tx_fee, raw_p2th_fee=p2th_fee, raw_amount=amount, cltv_timelock=cltv_timelock, new_inputs=new_inputs, debug=debug, reserve=reserve, reserve_address=reserve_address)
        
        return du.finalize_tx(rawtx, verify, sign, send)


    def release(self, proposal_txid: str, amount: str=None, change_address: str=None, tx_fee: str="0.01", p2th_fee: str="0.01", input_address: str=Settings.key.address, check_round: int=None, check_release: bool=False, wait: bool=False, new_inputs: bool=False, origin_label: str=None, origin_key: str=None, force: bool=False, sign: bool=False, send: bool=False, verify: bool=False) -> None: ### ADDRESSTRACK ###

        if (check_round is not None) or (wait == True):
            if not du.check_current_period(provider, proposal_txid, "donation", dist_round=check_round, wait=wait, release=True):
                return

        #if check_release:
        #    if not du.check_current_period(provider, proposal_txid, "donation", release=True, wait=wait):
        #        return

        use_slot = False if (amount is not None) else True

        params = { "id" : "DD" , "prp" : proposal_txid }

        basic_tx_data = du.get_basic_tx_data(provider, "donation", proposal_txid, input_address=Settings.key.address, new_inputs=new_inputs, use_slot=use_slot)

        rawtx = du.create_unsigned_trackedtx(params, basic_tx_data, change_address=change_address, raw_amount=amount, raw_tx_fee=tx_fee, raw_p2th_fee=p2th_fee, new_inputs=new_inputs, force=force)
        
        # TODO: in this configuration we can't use origin_label for P2SH. Look if it can be reorganized.
        if new_inputs:
            p2sh, prv, key, rscript = None, None, None, None
        else:
            p2sh = True
            key = Settings.key
            prv = provider
            rscript = basic_tx_data.get("redeem_script")

        return du.finalize_tx(rawtx, verify, sign, send, key=key, label=origin_label, provider=prv, redeem_script=rscript)

    def check_tx(self, txid=None, txhex=None):
        '''Creates a TrackedTransaction object and shows its properties. Primarily for debugging.'''
        tx = du.create_trackedtx(provider, txid=txid, txhex=txhex)
        pprint("Type: " + str(type(tx)))
        pprint(tx.__dict__)

    def check_all_tx(self, proposal_id: str, include_badtx: bool=False, light: bool=False):
        '''Lists all TrackedTransactions for a proposal, even invalid ones.
           include_badtx also detects wrongly formatted tranactions, but only displays the txid.'''
        du.get_all_trackedtxes(provider, proposal_id, include_badtx=include_badtx, light=light)

    def show_slot(self, proposal_id: str, satoshi: bool=False):
        '''Simplified variant of my_donation_states, only shows slot.'''
        dstates = du.get_donation_states(provider, proposal_id, address=Settings.key.address)
        # There must be only 1 state per proposal, so the
        try:
            if not satoshi:
                network_params = du.net_query(Settings.network)
                coin = int(1 / network_params.from_unit)
                slot = Decimal(dstates[0].slot) / coin 
            else:
                slot = dstates[0].slot
            print("Slot:", slot)

        except IndexError:
            print("No valid donation process found.")

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
