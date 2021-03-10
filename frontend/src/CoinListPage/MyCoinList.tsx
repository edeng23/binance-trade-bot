import React, {useEffect, useState} from 'react';
import axios, {AxiosResponse} from 'axios';
import styled from 'styled-components';
import {CoinContract} from "./CoinContract";
import Coin from "./Coin";


export const BackendRoute = 'http://localhost:5123'

const MyCoinList = () => {
    const [coins, setCoins] = useState<Array<CoinContract>>([]);

    const enableCoin = () => {
        return (symbol: string, enable: boolean) => {
            axios.get(`${BackendRoute}/api/coins/${symbol}?enable=${enable ? 'True' : 'False'}`)
                .then(() => {
                        const coinDup = [...coins]
                        const coinIndex = coinDup.findIndex(coin => coin.symbol === symbol);
                        const coin: CoinContract = coinDup.splice(coinIndex, 1)[0];
                        coin.enabled = enable;
                        coinDup.splice(coinIndex, 0, coin);
                        setCoins(coinDup);

                    }
                )
        }
    }

    useEffect(() => {
        axios
            .get(`${BackendRoute}/api/coins`)
            .then((response: AxiosResponse<Array<CoinContract>>) => {
                setCoins(response.data);
            });
    }, [])

    return (
        <MyCoinsListWrapper>
            {coins.map(coin =>
                <Coin key={coin.symbol} coin={coin} enableCoin={enableCoin()}/>
            )}
        </MyCoinsListWrapper>
    );
};

export default MyCoinList;

const MyCoinsListWrapper = styled.div`
margin-top: 2em;
  display: flex;
  width: 80%;
  align-self: center;
  flex-wrap: wrap;
`;

