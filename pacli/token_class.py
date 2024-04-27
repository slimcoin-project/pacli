from pacli.__main__ import Card as VanillaCard
from pacli.__main__ import Deck as VanillaDeck

# experimental idea: all card/deck commands go into Token.

class Token(VanillaDeck, VanillaCard):
    """Token commands manage the creation (spawning), issuance, transfer and information gathering about PeerAssets tokens.

    The token group can be used to replace both deck and card keywords, aimed to users not wanting to be exposed to the card-deck terminology.

    The deck command group can be used without any change, while the card group has the following differences:

    'card list' becomes 'token transfers'
    'card encode' becomes 'token encode_transfer'
    'card decode' becomes 'token decode_transfer'
    'card parse' becomes 'token parse_transfer'
    """

    def transfers(self, deck: str, quiet: bool=False, valid: bool=False, debug: bool=False):
        return VanillaCard().list(deck=deck, quiet=quiet, valid=valid, debug=debug)

    def encode_transfer(self, deckid: str, receiver: list=None, amount: list=None,
               asset_specific_data: str=None, json: bool=False):

        return VanillaCard().encode(deckid=deckid, receiver=receiver, amount=amount, asset_specific_data=asset_specific_data, json=json)

    def decode_transfer(self, hex: str):
        return VanillaCard().decode(hex=hex)

    def parse_transfer(self, deckid: str, cardid: str):
        return VanillaCard().parse(deckid=deckid, cardid=cardid)


