from pypeerassets.provider import RpcNode, Cryptoid, Explorer
from pypeerassets import pautils
from pacli.config import Settings

def set_up(provider):
    '''setup'''

    # if provider is local node, check if PA P2TH is loaded in local node
    # this handles indexing of transaction
    if Settings.provider == "rpcnode":
        if Settings.production:
            if not provider.listtransactions("PAPROD"):
                pautils.load_p2th_privkey_into_local_node(provider)
        if not Settings.production:
            if not provider.listtransactions("PATEST"):
                pautils.load_p2th_privkey_into_local_node(provider, prod=False)


def configured_provider(Settings):
    " resolve settings into configured provider "

    if Settings.provider.lower() == "rpcnode":
        _provider = RpcNode

    elif Settings.provider.lower() == "cryptoid":
        _provider = Cryptoid

    elif Settings.provider.lower() == "explorer":
        _provider = Explorer

    else:
        raise Exception('invalid provider.')

    ### MODIFIED - otherwise throws error because of network keyword ###
    if Settings.provider.lower() != "rpcnode":
        provider = _provider(network=Settings.network)
    else:
        provider = _provider(testnet=Settings.testnet, username=Settings.rpcuser, password=Settings.rpcpassword, ip=None, port=Settings.rpcport, directory=None)

    set_up(provider) # set_up() does not work
    ### END modified part ###

    return provider

provider = configured_provider(Settings)
