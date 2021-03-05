#!python3
import configparser
from binance.client import Client
import os
import networkx as nx
from networkx.algorithms.approximation import clique
import matplotlib.pyplot as plt

# Config consts
CFG_FL_NAME = 'user.cfg'
USER_CFG_SECTION = 'binance_user_config'

# Init config
config = configparser.ConfigParser()
if not os.path.exists('../'+CFG_FL_NAME):
    print('No configuration file (user.cfg) found! See README.')
    exit()
config.read('../'+CFG_FL_NAME)


# Get coin list from all_coins file
with open('all_coins') as f:
    all_coins = f.read().upper().splitlines()

def main():
    api_key = config.get(USER_CFG_SECTION, 'api_key')
    api_secret_key = config.get(USER_CFG_SECTION, 'api_secret_key')
    tld = config.get(USER_CFG_SECTION, 'tld') or 'com' # Default Top-level domain is 'com'

    client = Client(api_key, api_secret_key, tld=tld)
    
    available_tickers = {}
    for ticker in client.get_all_tickers():
        available_tickers[ticker['symbol']] = None
    
    G = nx.Graph()
    for coin in all_coins:
        for coin2 in all_coins:
            if coin != coin2 and (coin+coin2 in available_tickers) or (coin2+coin in available_tickers):
                #valid coin pair, add to graph
                G.add_edge(coin, coin2)

    f = plt.figure(figsize=(24,24), dpi=300)
    nx.draw(G, with_labels = True, node_size=600,font_size=16, font_color='red')
    f.savefig("coin_graph_all.png")
    
    remove = [node for node,degree in dict(G.degree()).items() if degree < 3]
    G.remove_nodes_from(remove)
    
    f2 = plt.figure(figsize=(24,24), dpi=300)
    nx.draw(G, with_labels = True, node_size=600,font_size=16, font_color='red')
    f2.savefig("coin_graph_three_pairs.png")

    remove = [node for node,degree in dict(G.degree()).items() if degree < 4]
    G.remove_nodes_from(remove)
    
    f3 = plt.figure(figsize=(24,24), dpi=300)
    nx.draw(G, with_labels = True, node_size=600,font_size=16, font_color='red')
    f3.savefig("coin_graph_four_pairs.png")
    
if __name__ == "__main__":
    main()