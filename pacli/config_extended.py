from pacli.config import conf_dir
import json, os

# This stores some settings in an additional config file, for example short keys for addresses, proposals, decks etc.
# An alternative for the future could be to use sqlite3 eventually.

EXT_CONFIGFILE = os.path.join(conf_dir, "extended_config.json")
CATEGORIES = ["address", "checkpoint", "deck", "proposal", "donation"]
CAT_INIT = {c : {} for c in CATEGORIES}

class ValueExistsError(Exception):
    pass

def get_config(configfilename: str=EXT_CONFIGFILE) -> dict:

    try:
        with open(configfilename, "r") as configfile:
            try:
                return json.load(configfile)
            except json.JSONDecodeError as e:
                if len(configfile.read()) == 0:
                    print("Empty file. Returning default config.")
                    return CAT_INIT
                else:
                    raise json.JSONDecodeError(e)
    except FileNotFoundError:
        print("File does not exist. Returning default config.")
        return CAT_INIT


def write_item(category: str, key: str, value: str, configfilename: str=EXT_CONFIGFILE, mode: str="protect", debug: bool=True) -> None:

    if debug:
        print("Storing: category: {}, key: {}, value: {}".format(category, key, value))
    config = get_config(configfilename)
    if debug:
        print("Old config:", config)


    if mode == "protect":
        if (key not in config[category]) or (not config[category][key]):
            config[category].update({key : value})
        else:
            raise ValueExistsError("Value already exists, you can't change it in protected mode.")
    elif (mode == "replace") or (key not in config[category]) or (type(config[category][key]) != list):
        config[category].update({key : value})
    elif mode == "add":
        # allows to manage lists
        config[category][key].append(value)

    with open(configfilename, "w") as configfile:
        json.dump(config, configfile)
    if debug:
        config = get_config(configfilename)
        print("New config:", config)

def read_item(category: str, key: str, configfilename: str=EXT_CONFIGFILE):
    #with open(configfilename, "r") as configfile:
    #    config = json.load(configfile)
    config = get_config(configfilename)
    return config[category][str(key)]

def delete_item(category: str, key: str, now: bool=False, configfilename: str=EXT_CONFIGFILE, debug: bool=True):
    config = get_config(configfilename)
    try:
        print("WARNING: deleting item from category {}, key: {}, value: {}".format(category, key, config[category][key]))
    except KeyError:
        raise ValueError("No item with this key. Nothing was deleted.")
    del config[category][key]
    if not now:
        print("This is a dry run. Use --now to delete irrecoverabily.")

    else:
        with open(configfilename, "w") as configfile:
            json.dump(config, configfile)
    if debug:
        print("New config file content:", config)

def search_value(category: str, value: str, configfilename: str=EXT_CONFIGFILE):
    config = get_config(configfilename)
    return [ key for key in config[category] if config[category][key] == value ]

def search_value_content(category: str, searchstring: str, configfilename: str=EXT_CONFIGFILE):
    config = get_config(configfilename)
    return [ key for key in config[category] if searchstring in config[category][key] ]

def process_fulllabel(fulllabel):
    # uses the network_label format
    label_split = fulllabel.split("_")
    network = label_split[0]
    label = "_".join(label_split[1:])
    return (network, label)




