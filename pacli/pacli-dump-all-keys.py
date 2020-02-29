import keyring
import secretstorage

bus = secretstorage.dbus_init()
collection = secretstorage.get_default_collection(bus)
for item in collection.search_items({'application': 'Python keyring library', "service" : "pacli"}):
    # print(item.get_label())
    print(item.get_attributes()["username"])
