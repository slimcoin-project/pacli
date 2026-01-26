import fire
from pacli.keystore import init_keystore
from pacli.coin import Coin
from pacli.extended.classes import ExtConfig, ExtAddress, ExtDeck, ExtCard, ExtTransaction
from pacli.at.classes import ATToken, PoBToken
from pacli.dt.classes import PoDToken, Proposal, Donation
from pacli.dex.classes import Swap
from pacli.extended.checkpoints import Checkpoint

# EXTENSION NOTE: pacli-extended overrides some vanilla methods.
# To do that cleanly, the original classes have been outsourced to a 'classes' module.
# 'classes' is imported by extended.classes module.
# The extended classes have the ExtCLASS syntax.

def main():

    init_keystore()

    from pacli.extended.token_class import Token

    fire.Fire({
        'config': ExtConfig(),
        'deck': ExtDeck(),
        'card': ExtCard(),
        'address': ExtAddress(),
        'transaction': ExtTransaction(),
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
