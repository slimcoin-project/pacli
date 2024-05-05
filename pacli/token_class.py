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

    def transfers(self, idstr: str, quiet: bool=False, valid: bool=False, debug: bool=False):
        """List all transactions (cards, i.e. issues, transfers, burns) of a token (with support for deck labels).

        Usage:

            pacli card list
            pacli token transfers

        Args:

          quiet: Suppresses additional output, printout in script-friendly way.
          valid: Only shows valid transactions according to Proof-of-Timeline rules, where no double spend has been recorded."""

        return VanillaCard().list(idstr=idstr, quiet=quiet, valid=valid, debug=debug)

    def encode_transfer(self, deckid: str, receiver: list=None, amount: list=None,
               asset_specific_data: str=None, json: bool=False):
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

        return VanillaCard().encode(deckid=deckid, receiver=receiver, amount=amount, asset_specific_data=asset_specific_data, json=json)

    def decode_transfer(self, encoded: str):
        """Decodes a token transfer (card) protobuf string.

        Usage:

            pacli card decode HEX
            pacli token decode_transfer HEX

        HEX is the encoded transaction/card in protobuf format (see 'card decode'/'token decode')"""
        return VanillaCard().decode(encoded=encoded)

    def parse_transfer(self, deckid: str, cardid: str):
        """Parses a token transfer (card) from txid and print data.

        Usage:

             pacli card parse DECKID CARDID
             pacli token parse_transfer DECKID CARDID

        CARDID is the transaction ID of the card.
        """
        return VanillaCard().parse(deckid=deckid, cardid=cardid)


