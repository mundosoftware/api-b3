from get_price_cryptocurrencies import updateCryptos
from lists import fiis, bdrs, stocks, etfs
import requests
from bs4 import BeautifulSoup
from get_data_internet import getAllValuesFiis, getAllValuesStocks, getAllValuesEtfs, getAllValuesBdrs

totalStocks = stocks + fiis + bdrs + etfs

print("Rodando dnv")
updateCryptos()
for typeStock in totalStocks:
    if typeStock in stocks:

        url = requests.get(
            f"https://statusinvest.com.br/acoes/{typeStock}")
        nav = BeautifulSoup(url.text, "html5lib")

        infoAction = getAllValuesStocks(nav, typeStock.upper())
        print(f"Atualizando a ação: {typeStock}")

    elif typeStock in fiis:

        url = requests.get(
            f"https://statusinvest.com.br/fundos-imobiliarios/{typeStock}")
        nav = BeautifulSoup(url.text, "html5lib")

        infoAction = getAllValuesFiis(nav, typeStock.upper())
        print(f"Atualizando o fundo: {typeStock}")

    elif typeStock in etfs:
        url = requests.get(
            f"https://statusinvest.com.br/etfs/{typeStock}")
        nav = BeautifulSoup(url.text, "html5lib")

        infoAction = getAllValuesEtfs(nav, typeStock.upper())
        print(f"Atualizando o ETF: {typeStock}")

    else:
        url = requests.get(
            f"https://statusinvest.com.br/bdrs/{typeStock}")
        nav = BeautifulSoup(url.text, "html5lib")

        infoAction = getAllValuesBdrs(nav, typeStock.upper())
        print(f"Atualizando o BDR: {typeStock}")
