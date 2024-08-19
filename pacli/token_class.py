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

    def transfers(self, idstr: str, address: str=None, quiet: bool=False, valid: bool=False, show_invalid: bool=False, only_invalid: bool=False, debug: bool=False):
        """List all transactions (cards or CardTransfers, i.e. issues, transfers, burns) of a token.

        Usage:

            pacli card list TOKEN
            pacli token transfers TOKEN

        TOKEN can be a token (deck) ID or a label.
        In standard mode, only valid transfers will be shown.
        In compatibility mode, standard output includes some invalid transfers: those in valid transactions which aren't approved by the Proof-of-Timeline rules.

        Args:

          address: Filter transfers by address. Labels are permitted. If no address is given after -a, use the current main address.
          quiet: Suppresses additional output, printout in script-friendly way.
          show_invalid: If compatibility mode is turned off, with this flag on also invalid transfers are shown.
          only_invalid: Show only invalid transfers.
          valid: If compatibility mode is turned on, this shows valid transactions according to Proof-of-Timeline rules, where no double spend has been recorded.
          debug: Show debug information."""

        return VanillaCard().list(idstr=idstr, address=address, quiet=quiet, valid=valid, show_invalid=show_invalid, only_invalid=only_invalid, debug=debug)

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


